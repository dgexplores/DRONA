"""Set every account's password to its own employee ID.

TESTING ONLY. The deployed service is reachable at a public URL, so this makes
every account - including the Super Admin - publicly guessable and is recorded
in the README on purpose, for the duration of testing.

Re-lock with:  python manage.py set_admin_password  (rotates the Super Admin),
then rotate the rest by hand - see ROADMAP.md.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "TESTING ONLY: set every user's password to their own employee ID."

    def add_arguments(self, parser):
        parser.add_argument(
            "--role",
            choices=["staff", "hod", "admin"],
            help="Limit to one role instead of resetting every account.",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Skip the confirmation prompt (needed for non-interactive use).",
        )

    def handle(self, *args, **options):
        StaffUser = get_user_model()
        qs = StaffUser.objects.all()
        if options["role"]:
            qs = qs.filter(role=options["role"])
        users = list(qs.order_by("employee_id"))

        if not users:
            raise CommandError("No accounts matched; nothing to reset.")

        self.stdout.write(self.style.WARNING(
            "TESTING MODE: this makes every account - including the Super Admin -"
        ))
        self.stdout.write(self.style.WARNING(
            "guessable by anyone who can reach the site. Do NOT run on a real deployment."
        ))
        self.stdout.write(f"About to set {len(users)} password(s) to the matching employee ID.")
        for u in users:
            self.stdout.write(f"  {u.employee_id:<10} {u.get_role_display():<18} -> {u.employee_id}")

        if not options["yes"]:
            answer = input("\nType 'reset' to continue: ").strip()
            if answer != "reset":
                raise CommandError("Aborted; no passwords were changed.")

        for u in users:
            u.set_password(u.employee_id)
            u.is_active = True
            u.save(update_fields=["password", "is_active"])

        self.stdout.write(self.style.SUCCESS(
            f"Reset {len(users)} password(s) for TESTING. Re-lock before any real use - see README."
        ))
