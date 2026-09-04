from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0005_product_hidden_by_farmer'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='rejected_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='product',
            name='rejection_reason',
            field=models.CharField(blank=True, max_length=255),
        ),
    ]