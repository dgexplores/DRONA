import os
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.cache import cache
from apps.users.models import Department, StaffUser


class AuthTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name="IT", code="IT")
        self.staff = StaffUser.objects.create_user(
            employee_id="EMP100",
            username="emp100",
            email="emp100@srms.ac.in",
            first_name="Test",
            last_name="User",
            password="pass12345",
            department=self.dept,
            role="staff",
        )

    def test_login_with_employee_id(self):
        resp = self.client.post(reverse('login'), {
            'employee_id': 'EMP100', 'password': 'pass12345'
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.staff.pk)

    def test_login_wrong_password(self):
        resp = self.client.post(reverse('login'), {
            'employee_id': 'EMP100', 'password': 'wrong'
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Invalid")

    def test_unknown_employee_id_still_runs_the_password_hasher(self):
        """An unknown ID must cost the same as a wrong password.

        Regression guard for the enumeration oracle: the previous hand-rolled
        lookup returned early when no user matched, so response time leaked
        whether an Employee ID existed even though the message was generic.
        ModelBackend hashes a dummy password to equalise the cost.
        """
        from unittest import mock
        with mock.patch.object(StaffUser, 'set_password') as set_password:
            resp = self.client.post(reverse('login'), {
                'employee_id': 'NOSUCHID', 'password': 'whatever123'
            })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Invalid Employee ID or Password")
        self.assertTrue(
            set_password.called,
            "ModelBackend must hash a dummy password for unknown accounts",
        )

    def test_login_is_case_insensitive_on_employee_id(self):
        resp = self.client.post(reverse('login'), {
            'employee_id': '  emp100  ', 'password': 'pass12345'
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.staff.pk)

    def test_dashboard_requires_login(self):
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 302)

    def test_profile_requires_login(self):
        resp = self.client.get(reverse('profile'))
        self.assertEqual(resp.status_code, 302)

    def test_logged_in_profile(self):
        self.client.login(employee_id='EMP100', password='pass12345')
        resp = self.client.get(reverse('profile'))
        self.assertEqual(resp.status_code, 200)


class RegistrationApprovalTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name="IT", code="IT")
        self.admin = StaffUser.objects.create_user(
            employee_id="ADMIN9", username="admin9",
            email="admin9@srms.ac.in", password="pass12345",
            role="admin", is_superuser=True,
        )

    def test_register_creates_inactive_user(self):
        cache.clear()
        resp = self.client.post(reverse('register'), {
            'employee_id': 'EMP777', 'first_name': 'New', 'last_name': 'User',
            'email': 'new@srms.ac.in', 'department': self.dept.id,
            'designation': 'Lab Assistant', 'phone_number': '12345',
            'password1': 'secret123', 'password2': 'secret123',
        })
        self.assertEqual(resp.status_code, 302)
        user = StaffUser.objects.get(employee_id='EMP777')
        self.assertFalse(user.is_active)
        self.assertEqual(user.role, 'staff')

    def test_register_rejects_duplicate_employee_id(self):
        cache.clear()
        StaffUser.objects.create_user(
            employee_id="EMP778", username="emp778",
            email="a@b.com", password="pass12345", role="staff",
        )
        resp = self.client.post(reverse('register'), {
            'employee_id': 'EMP778', 'first_name': 'A', 'last_name': 'B',
            'email': 'x@srms.ac.in', 'password1': 'secret123', 'password2': 'secret123',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "already registered")

    def test_register_rejects_duplicate_email(self):
        """Duplicate emails break password-reset disambiguation; registration must refuse them."""
        cache.clear()
        StaffUser.objects.create_user(
            employee_id="EMP783", username="emp783",
            email="dup@srms.ac.in", password="pass12345", role="staff",
        )
        resp = self.client.post(reverse('register'), {
            'employee_id': 'EMP784', 'first_name': 'A', 'last_name': 'B',
            'email': 'dup@srms.ac.in', 'password1': 'secret123', 'password2': 'secret123',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "already registered")
        self.assertFalse(StaffUser.objects.filter(employee_id='EMP784').exists())

    def test_logout_requires_post(self):
        """GET logout was a CSRF-less state change; only POST must log out."""
        StaffUser.objects.create_user(
            employee_id="EMP785", username="emp785",
            email="e@b.com", password="pass12345", role="staff",
        )
        self.client.login(employee_id='EMP785', password='pass12345')
        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)
        self.assertIn('_auth_user_id', self.client.session)
        resp = self.client.post(reverse('logout'))
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_login_pending_uses_generic_error(self):
        user = StaffUser.objects.create_user(
            employee_id="EMP779", username="emp779",
            email="a@b.com", password="pass12345", role="staff", is_active=False,
        )
        resp = self.client.post(reverse('login'), {
            'employee_id': 'EMP779', 'password': 'pass12345'
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Invalid Employee ID or Password")
        self.assertNotContains(resp, "pending admin approval")

    def test_login_wrong_password_does_not_reveal_pending_account(self):
        StaffUser.objects.create_user(
            employee_id="EMP778", username="emp778",
            email="a@b.com", password="pass12345", role="staff", is_active=False,
        )
        resp = self.client.post(reverse('login'), {
            'employee_id': 'EMP778', 'password': 'wrongpass'
        })
        self.assertContains(resp, "Invalid Employee ID or Password")
        self.assertNotContains(resp, "pending admin approval")

    def test_approve_user_enables_login(self):
        user = StaffUser.objects.create_user(
            employee_id="EMP780", username="emp780",
            email="a@b.com", password="pass12345", role="staff", is_active=False,
        )
        self.client.login(employee_id='ADMIN9', password='pass12345')
        resp = self.client.post(reverse('approve_user', args=[user.id]))
        self.assertEqual(resp.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    def test_non_admin_cannot_approve(self):
        staff = StaffUser.objects.create_user(
            employee_id="EMP781", username="emp781",
            email="a@b.com", password="pass12345", role="staff",
        )
        pending = StaffUser.objects.create_user(
            employee_id="EMP782", username="emp782",
            email="a@b.com", password="pass12345", role="staff", is_active=False,
        )
        self.client.login(employee_id='EMP781', password='pass12345')
        resp = self.client.post(reverse('approve_user', args=[pending.id]))
        self.assertEqual(resp.status_code, 403)
        self.assertTemplateUsed(resp, 'errors/403.html')


class LanguageToggleTests(TestCase):
    def setUp(self):
        self.staff = StaffUser.objects.create_user(
            employee_id="EMP101", username="emp101",
            email="a@b.com", password="pass12345", role="staff"
        )
        self.client.login(employee_id='EMP101', password='pass12345')

    def test_toggle_language(self):
        resp = self.client.get(reverse('toggle_language'), {'lang': 'hi'})
        self.assertEqual(resp.status_code, 302)
        self.staff.refresh_from_db()
        self.assertEqual(self.staff.preferred_language, 'hi')

    def test_dashboard_renders_hindi(self):
        self.staff.preferred_language = 'hi'
        self.staff.save()
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "पाठ्यक्रम", status_code=200)

    def test_toggle_works_for_anonymous_via_session(self):
        self.client.logout()
        resp = self.client.get(reverse('toggle_language'), {'lang': 'hi'})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.client.session.get('django_language'), 'hi')
        resp = self.client.get(reverse('login'))
        self.assertContains(resp, "English")


class SecurityHeadersTests(TestCase):
    def test_csp_and_security_headers_present(self):
        resp = self.client.get(reverse('login'))
        self.assertIn('Content-Security-Policy', resp.headers)
        self.assertIn('Referrer-Policy', resp.headers)
        self.assertIn('Permissions-Policy', resp.headers)
        self.assertIn("object-src 'none'", resp.headers['Content-Security-Policy'])
        self.assertIn("frame-ancestors 'none'", resp.headers['Content-Security-Policy'])


class ListUsersCommandTests(TestCase):
    def test_emails_masked_by_default(self):
        """list_users must not print PII to logs unless explicitly asked."""
        from django.core.management import call_command
        from io import StringIO
        StaffUser.objects.create_user(
            employee_id="EMP900", username="emp900",
            email="private@srms.ac.in", password="pass12345", role="staff",
        )
        out = StringIO()
        call_command('list_users', stdout=out)
        self.assertNotIn('private@srms.ac.in', out.getvalue())
        self.assertIn('***@srms.ac.in', out.getvalue())

    def test_include_email_flag_shows_full_address(self):
        from django.core.management import call_command
        from io import StringIO
        StaffUser.objects.create_user(
            employee_id="EMP901", username="emp901",
            email="shown@srms.ac.in", password="pass12345", role="staff",
        )
        out = StringIO()
        call_command('list_users', '--include-email', stdout=out)
        self.assertIn('shown@srms.ac.in', out.getvalue())


class RegisterRateLimitTests(TestCase):
    def test_register_ratelimited_after_limit(self):
        cache.clear()
        url = reverse('register')
        payload = {
            'employee_id': 'EMP999', 'first_name': 'Rate', 'last_name': 'Limit',
            'email': 'rate@srms.ac.in', 'password1': 'secret123', 'password2': 'secret123',
        }
        # Trigger the per-IP rate limit: 3 allowed, the 4th should be limited.
        for i in range(3):
            self.client.post(url, {**payload, 'employee_id': f'EMP99{i}', 'email': f'rate{i}@srms.ac.in'})
        resp = self.client.post(url, {**payload, 'employee_id': 'EMPRATE', 'email': 'rateX@srms.ac.in'})
        self.assertEqual(resp.status_code, 429)
        self.assertIn("Too many sign-up attempts", resp.content.decode())


class ProductionSettingsGuardTests(TestCase):
    """Settings must refuse to boot with dev defaults in production.

    Exercised in a subprocess because the guard runs at import time and cannot
    be triggered by re-importing inside an already-initialised interpreter.
    """

    INSECURE_DEFAULT_KEY = 'django-insecure-)4*0dtz+)3g^hrq2q82^@yazj*o92yyf8r5sxfx+35c0r9bodf'
    STRONG_KEY = 'a-sufficiently-long-random-value-for-tests'

    def _import_settings(self, **env_overrides):
        import os
        import subprocess
        import sys
        from django.conf import settings as dj_settings

        env = dict(os.environ)
        # Explicit values win over any developer .env, which load_dotenv()
        # would otherwise fill in and mask the guard.
        env.update(env_overrides)
        return subprocess.run(
            [sys.executable, '-c', 'import srms_dorna.settings'],
            cwd=str(dj_settings.BASE_DIR),
            env=env, capture_output=True, text=True, timeout=60,
        )

    def test_insecure_default_secret_key_is_rejected(self):
        result = self._import_settings(
            DJANGO_DEBUG='False',
            DJANGO_SECRET_KEY=self.INSECURE_DEFAULT_KEY,
            DJANGO_ALLOWED_HOSTS='example.com',
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DJANGO_SECRET_KEY', result.stderr)

    def test_wildcard_allowed_hosts_is_rejected(self):
        result = self._import_settings(
            DJANGO_DEBUG='False',
            DJANGO_SECRET_KEY=self.STRONG_KEY,
            DJANGO_ALLOWED_HOSTS='*',
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DJANGO_ALLOWED_HOSTS', result.stderr)

    def test_explicit_production_config_loads(self):
        result = self._import_settings(
            DJANGO_DEBUG='False',
            DJANGO_SECRET_KEY=self.STRONG_KEY,
            DJANGO_ALLOWED_HOSTS='example.com',
        )
        self.assertEqual(result.returncode, 0, result.stderr)


class HindiCatalogTests(TestCase):
    """The Hindi UI depends on a committed catalog, not on a code flag.

    Guards three separate ways this has silently broken:
      * LOCALE_PATHS pointing nowhere (no LANGUAGES / LOCALE_PATHS before this)
      * a .po present but no compiled .mo (Render's image has no msgfmt)
      * a msgid in a template that the catalog never learned
    """

    def test_locale_paths_and_languages_configured(self):
        from django.conf import settings
        self.assertTrue(settings.LOCALE_PATHS, 'LOCALE_PATHS is empty')
        self.assertIn('hi', dict(settings.LANGUAGES))

    def test_compiled_mo_is_committed(self):
        from django.conf import settings
        mo = os.path.join(str(settings.LOCALE_PATHS[0]), 'hi', 'LC_MESSAGES', 'django.mo')
        self.assertTrue(os.path.exists(mo), 'django.mo missing - run compilemessages and commit it')

    def test_catalog_translates_known_strings(self):
        from django.utils import translation
        with translation.override('hi'):
            for src, expected in [
                ('Dashboard', 'डैशबोर्ड'),
                ('Employee ID', 'कर्मचारी आईडी'),
                ('Sign In', 'साइन इन करें'),
                ('Certificates', 'प्रमाणपत्र'),
                ('Password', 'पासवर्ड'),
            ]:
                self.assertEqual(translation.gettext(src), expected, f'{src!r} not translated')

    def test_session_language_activates_catalog(self):
        """The toggle writes the session; {% trans %} must follow it.

        LocaleMiddleware reads only the language cookie and Accept-Language, so
        this is UserLanguageMiddleware's job (apps/users/views.py toggle_language).
        """
        dept = Department.objects.create(name="IT", code="IT")
        StaffUser.objects.create_user(
            employee_id="EMPH1", username="emph1", email="emph1@srms.ac.in",
            password="pass12345", role="staff", department=dept,
        )
        self.client.login(employee_id='EMPH1', password='pass12345')
        self.client.get(reverse('toggle_language'), {'lang': 'hi'})
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'पाठ्यक्रम')
        self.assertNotContains(resp, 'Enrolled Courses')

    def test_saved_preference_applies_on_a_fresh_session(self):
        """A saved Hindi preference must win even with an empty session."""
        dept = Department.objects.create(name="IT", code="IT")
        u = StaffUser.objects.create_user(
            employee_id="EMPH2", username="emph2", email="emph2@srms.ac.in",
            password="pass12345", role="staff", department=dept, preferred_language="hi",
        )
        self.client.login(employee_id='EMPH2', password='pass12345')
        resp = self.client.get(reverse('dashboard'))
        self.assertContains(resp, 'पाठ्यक्रम')
        u.refresh_from_db()
        self.assertEqual(u.preferred_language, 'hi')


class AdminPasswordSyncTests(TestCase):
    """`seed.py` and `set_admin_password` must never disagree about the admin password.

    They are two writers of the same field. `boot` calls set_admin_password on every
    start, so if the seed used a different env var the deployed password would
    silently be whichever ran last.
    """

    def _admin(self):
        return StaffUser.objects.create_superuser(
            employee_id='ADMIN001', username='admin', email='admin@srms.ac.in',
            first_name='Super', last_name='Admin', password='placeholder-old',
        )

    def test_set_admin_password_rotates_from_env(self):
        self._admin()
        with mock.patch.dict(os.environ, {'DJANGO_ADMIN_PASSWORD': 'FromEnv123'}):
            call_command('set_admin_password')
        u = StaffUser.objects.get(employee_id='ADMIN001')
        self.assertTrue(u.check_password('FromEnv123'))

    def test_seed_and_command_read_the_same_env_var(self):
        import importlib
        with mock.patch.dict(os.environ, {'DJANGO_ADMIN_PASSWORD': 'Shared123'}):
            importlib.reload(importlib.import_module('seed'))
            importlib.reload(importlib.import_module('seed'))
        self.assertEqual(importlib.import_module('seed').SEED_ADMIN_PASSWORD, 'Shared123')

    def test_seed_resyncs_an_existing_admin(self):
        self._admin()
        u = StaffUser.objects.get(employee_id='ADMIN001')
        u.set_password('something-else')
        u.save()
        import importlib
        seed = importlib.import_module('seed')
        seed.create_super_admin()
        u.refresh_from_db()
        self.assertTrue(u.check_password(seed.SEED_ADMIN_PASSWORD))


class HodRoleTests(TestCase):
    """The tier below Super Admin is Head of Department. 'trainer' no longer exists."""

    def test_trainer_is_not_a_valid_role(self):
        self.assertNotIn('trainer', dict(StaffUser.ROLE_CHOICES))
        self.assertIn('hod', dict(StaffUser.ROLE_CHOICES))

    def test_hod_is_a_manager(self):
        hod = StaffUser.objects.create_user(
            employee_id='HOD_IT', username='hod_it', email='hod_it@srms.ac.in',
            password='HOD_IT', role='hod',
        )
        self.assertTrue(hod.is_manager)
        self.assertFalse(hod.is_super_admin)

    def test_plain_staff_is_not_a_manager(self):
        s = StaffUser.objects.create_user(
            employee_id='EMPX', username='empx', email='empx@srms.ac.in',
            password='drona123', role='staff',
        )
        self.assertFalse(s.is_manager)

    def test_hod_reaches_management_console(self):
        hod = StaffUser.objects.create_user(
            employee_id='HOD_IT', username='hod_it', email='hod_it@srms.ac.in',
            password='HOD_IT', role='hod',
        )
        self.client.force_login(hod)
        r = self.client.get(reverse('mgmt_home'))
        self.assertEqual(r.status_code, 200)


class DatabaseConnectionTests(SimpleTestCase):
    """Managed Postgres drops idle SSL sockets; Django must notice and reconnect.

    Regression guard: without CONN_HEALTH_CHECKS the app returns 500
    ("SSL connection has been closed unexpectedly") to whichever unlucky user
    arrives after the provider closes an idle connection.
    """

    def test_postgres_config_enables_health_checks(self):
        from srms_dorna.settings import postgres_config
        cfg = postgres_config('postgresql://u:p@db.example.invalid:5432/name')
        self.assertTrue(cfg.get('CONN_HEALTH_CHECKS'),
                        'conn_health_checks must stay on for managed Postgres')
        self.assertEqual(cfg.get('CONN_MAX_AGE'), 600)
