from django.db import migrations


def trainer_to_hod(apps, schema_editor):
    StaffUser = apps.get_model("users", "StaffUser")
    StaffUser.objects.filter(role="trainer").update(role="hod")
    # The old demo HOD account (EMP010, designation "HOD, Computer & IT Lab") is
    # superseded by HOD_<DEPT_CODE>. Demoted rather than deleted so its
    # enrollments / certificates / attempts keep their FKs intact.
    StaffUser.objects.filter(employee_id="EMP010").update(
        role="staff", designation="Senior Staff"
    )


def hod_to_trainer(apps, schema_editor):
    StaffUser = apps.get_model("users", "StaffUser")
    StaffUser.objects.filter(role="hod").exclude(
        employee_id__startswith="HOD_"
    ).update(role="trainer")


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0003_alter_staffuser_role"),
    ]

    operations = [
        migrations.RunPython(trainer_to_hod, hod_to_trainer),
    ]
