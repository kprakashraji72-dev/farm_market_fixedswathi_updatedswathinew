# Generated for: product approval workflow, cost price, and damage log
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inventory', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='cost_price',
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=8, null=True,
                help_text='What this product costs you per unit. Optional — used to show profit on the farm report.'
            ),
        ),
        migrations.AddField(
            model_name='product',
            name='is_approved',
            field=models.BooleanField(
                default=True,
                help_text='Must be True for the product to appear on the customer-facing store. '
                           'Farmer-added products start False until an admin approves them.'
            ),
        ),
        migrations.AddField(
            model_name='product',
            name='approved_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='product',
            name='approved_by',
            field=models.ForeignKey(
                blank=True, limit_choices_to={'role': 'admin'}, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='approved_products', to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.CreateModel(
            name='ProductDamage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.PositiveIntegerField()),
                ('note', models.CharField(blank=True, max_length=255, help_text='Optional reason, e.g. "spoiled in transit".')),
                ('reported_at', models.DateTimeField(auto_now_add=True)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='damages', to='inventory.product')),
            ],
            options={
                'ordering': ['-reported_at'],
            },
        ),
    ]
