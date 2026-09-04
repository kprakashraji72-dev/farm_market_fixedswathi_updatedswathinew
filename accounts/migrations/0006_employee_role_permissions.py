import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('accounts', '0005_seed_sample_admin'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[
                    ('admin', 'Admin'), ('customer', 'Customer'),
                    ('driver', 'Driver'), ('farmer', 'Farmer'), ('employee', 'Employee'),
                ],
                default='customer', max_length=20,
                help_text='Determines dashboard access and post-login redirect.',
            ),
        ),
        migrations.CreateModel(
            name='EmployeePermission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('can_manage_orders', models.BooleanField(default=False, help_text='View/update order status, assign drivers.')),
                ('can_manage_inventory', models.BooleanField(default=False, help_text='Manage store products & categories (not farm profiles or farmer verification).')),
                ('can_view_reports', models.BooleanField(default=False, help_text='View the sales/inventory reports page (read-only).')),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(
                    limit_choices_to={'role': 'employee'}, on_delete=django.db.models.deletion.CASCADE,
                    related_name='employee_permission', to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Employee permission',
                'verbose_name_plural': 'Employee permissions',
            },
        ),
    ]
