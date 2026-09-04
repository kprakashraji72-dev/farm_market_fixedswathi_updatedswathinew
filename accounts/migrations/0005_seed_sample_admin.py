"""
Seeds one ready-to-use admin account the first time `migrate` runs, so
there's no need to run `createsuperuser` by hand just to get into
/dashboard/. Safe to re-run: it only creates the account if a user with
this username doesn't already exist, so it won't clobber anything if
you've since changed the password or created your own admin.

Login:  username = admin      password = Admin@12345
Change the password after first login (Profile page, or
`python manage.py changepassword admin`).
"""
from django.contrib.auth.hashers import make_password
from django.db import migrations


def create_sample_admin(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    if User.objects.filter(username='admin').exists():
        return
    User.objects.create(
        username='admin',
        email='admin@freshtrace.local',
        password=make_password('Admin@12345'),
        role='admin',
        is_verified=True,
        is_staff=True,
        is_superuser=True,
        is_active=True,
    )


def remove_sample_admin(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    User.objects.filter(username='admin', email='admin@freshtrace.local').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_alter_user_managers'),
    ]

    operations = [
        migrations.RunPython(create_sample_admin, remove_sample_admin),
    ]
