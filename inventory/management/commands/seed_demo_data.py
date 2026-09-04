"""
Optional helper for local testing: creates a demo admin, farmer, driver,
customer, a couple of categories/farms/products.
Run with: python manage.py seed_demo_data
"""
from django.core.management.base import BaseCommand
from accounts.models import User
from inventory.models import Category, Farm, Product


class Command(BaseCommand):
    help = 'Seeds demo users, farms, categories and products for local testing.'

    def handle(self, *args, **options):
        admin, _ = User.objects.get_or_create(
            username='admin', defaults={'role': User.Role.ADMIN, 'is_staff': True, 'is_superuser': True}
        )
        admin.set_password('admin12345')
        admin.role = User.Role.ADMIN
        admin.is_staff = True
        admin.is_superuser = True
        admin.save()

        driver, _ = User.objects.get_or_create(
            username='driver1', defaults={'role': User.Role.DRIVER, 'is_verified': True}
        )
        driver.set_password('driver12345')
        driver.role = User.Role.DRIVER
        driver.is_verified = True
        driver.save()

        customer, _ = User.objects.get_or_create(
            username='customer1', defaults={'role': User.Role.CUSTOMER}
        )
        customer.set_password('customer12345')
        customer.save()

        veg, _ = Category.objects.get_or_create(name='Vegetables', icon='fa-carrot')
        fruit, _ = Category.objects.get_or_create(name='Fruits', icon='fa-apple-whole')

        farm, _ = Farm.objects.get_or_create(
            name='Green Valley Farm',
            defaults={'location': 'Nashik, Maharashtra', 'description': 'Family-run organic farm since 1998.'}
        )

        Product.objects.get_or_create(
            name='Fresh Tomatoes', farm=farm, category=veg,
            defaults={'price': 2.50, 'unit': 'kg', 'stock_quantity': 100}
        )
        Product.objects.get_or_create(
            name='Organic Apples', farm=farm, category=fruit,
            defaults={'price': 3.20, 'unit': 'kg', 'stock_quantity': 80}
        )

        self.stdout.write(self.style.SUCCESS(
            'Seeded: admin/admin12345, driver1/driver12345, customer1/customer12345'
        ))
