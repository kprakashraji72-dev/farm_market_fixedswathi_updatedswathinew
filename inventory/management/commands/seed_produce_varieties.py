"""
Management command to seed realistic produce varieties (Carrots, Apples, Tomatoes, Potatoes, etc.)
for testing and demonstrating the Smart Search & Recommendation Engine.
"""
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from inventory.models import Category, Farm, Product


class Command(BaseCommand):
    help = 'Seeds realistic produce varieties for the Smart Recommendation engine'

    def handle(self, *args, **options):
        self.stdout.write('Seeding produce varieties for smart recommendations...')

        # Ensure categories exist
        veg_cat, _ = Category.objects.get_or_create(
            slug='vegetables',
            defaults={'name': 'Vegetables', 'icon': 'fa-carrot'}
        )
        fruit_cat, _ = Category.objects.get_or_create(
            slug='fruits',
            defaults={'name': 'Fruits', 'icon': 'fa-apple-whole'}
        )

        # Ensure farm exists
        farm = Farm.objects.first()
        if not farm:
            farm = Farm.objects.create(
                name='Green Valley Organic Farm',
                slug='green-valley-organic-farm',
                location='Ooty Nilgiris',
                description='Certified chemical-free mountain farm practicing sustainable regenerative agriculture.'
            )

        # List of realistic produce varieties
        varieties = [
            # --- CARROT VARIETIES ---
            {
                'name': 'Small Carrot',
                'category': veg_cat,
                'price': Decimal('60.00'),
                'unit': 'kg',
                'stock': 85,
                'description': 'Crisp and sweet tender small carrots, ideal for daily salads and light stir-fries.',
                'image': 'products/vibrant-orange-carrot-with-fresh-green-tops-isolated-against-black-background__1hjv5rX.avif'
            },
            {
                'name': 'Regular Carrot',
                'category': veg_cat,
                'price': Decimal('70.00'),
                'unit': 'kg',
                'stock': 120,
                'description': 'Standard fresh harvest carrots packed with Vitamin A and rich natural sweetness.',
                'image': 'products/vibrant-orange-carrot-with-fresh-green-tops-isolated-against-black-background__Y8WfVlV.avif'
            },
            {
                'name': 'Ooty Carrot',
                'category': veg_cat,
                'price': Decimal('80.00'),
                'unit': 'kg',
                'stock': 95,
                'description': 'Famous mountain-grown Ooty carrots with distinct crunchiness, deep orange hue, and rich juiciness.',
                'image': 'products/vibrant-orange-carrot-with-fresh-green-tops-isolated-against-black-background__1hjv5rX.avif'
            },
            {
                'name': 'Baby Carrot',
                'category': veg_cat,
                'price': Decimal('85.00'),
                'unit': 'kg',
                'stock': 50,
                'description': 'Delicate, petite gourmet baby carrots harvested early for optimal tenderness and sweetness.',
                'image': 'products/vibrant-orange-carrot-with-fresh-green-tops-isolated-against-black-background__Y8WfVlV.avif'
            },
            {
                'name': 'Organic Carrot',
                'category': veg_cat,
                'price': Decimal('90.00'),
                'unit': 'kg',
                'stock': 70,
                'description': '100% pesticide-free zero-chemical organic farm carrots grown in certified bio-rich soil.',
                'image': 'products/vibrant-orange-carrot-with-fresh-green-tops-isolated-against-black-background__1hjv5rX.avif'
            },

            # --- RELATED ROOT VEGETABLES (YOU MAY ALSO LIKE) ---
            {
                'name': 'Beetroot',
                'category': veg_cat,
                'price': Decimal('45.00'),
                'unit': 'kg',
                'stock': 90,
                'description': 'Deep ruby-red fresh beetroots rich in antioxidants, dietary nitrates, and iron.',
                'image': 'products/images_3.jpg'
            },
            {
                'name': 'Radish',
                'category': veg_cat,
                'price': Decimal('35.00'),
                'unit': 'kg',
                'stock': 65,
                'description': 'Crisp, peppery white radishes freshly plucked with crisp green tops.',
                'image': 'products/images_4.jpg'
            },
            {
                'name': 'Farm Fresh Potato',
                'category': veg_cat,
                'price': Decimal('40.00'),
                'unit': 'kg',
                'stock': 200,
                'description': 'Versatile, earthy golden potatoes harvested from pesticide-free sandy loam fields.',
                'image': 'products/veg.jpg'
            },
            {
                'name': 'Sweet Potato',
                'category': veg_cat,
                'price': Decimal('55.00'),
                'unit': 'kg',
                'stock': 75,
                'description': 'Naturally caramelized nutritious sweet potatoes loaded with dietary fiber.',
                'image': 'products/images_2.jpg'
            },

            # --- APPLE VARIETIES ---
            {
                'name': 'Shimla Royal Apple',
                'category': fruit_cat,
                'price': Decimal('120.00'),
                'unit': 'kg',
                'stock': 80,
                'description': 'Juicy, fragrant Himachal mountain apples with crisp texture and vibrant red blush.',
                'image': 'products/images_2.jpg'
            },
            {
                'name': 'Kashmir Royal Apple',
                'category': fruit_cat,
                'price': Decimal('150.00'),
                'unit': 'kg',
                'stock': 110,
                'description': 'Sweet, aromatic premium Kashmir valley apples with golden-red skin and dense crunch.',
                'image': 'products/images_3.jpg'
            },
            {
                'name': 'Green Granny Smith Apple',
                'category': fruit_cat,
                'price': Decimal('180.00'),
                'unit': 'kg',
                'stock': 40,
                'description': 'Tart, refreshing imported crisp green apples favored for healthy juicing and baking.',
                'image': 'products/images_4.jpg'
            },

            # --- TOMATO VARIETIES ---
            {
                'name': 'Country Tomato (Nati)',
                'category': veg_cat,
                'price': Decimal('30.00'),
                'unit': 'kg',
                'stock': 150,
                'description': 'Tangy, juicy heirloom country tomatoes ideal for curries, rasam, and traditional gravies.',
                'image': 'products/veg.jpg'
            },
            {
                'name': 'Hybrid Table Tomato',
                'category': veg_cat,
                'price': Decimal('40.00'),
                'unit': 'kg',
                'stock': 180,
                'description': 'Firm, thick-skinned round table tomatoes with mild acidity and high slicing yield.',
                'image': 'products/veg_pmtc8TV.jpg'
            },
            {
                'name': 'Cherry Tomato',
                'category': veg_cat,
                'price': Decimal('65.00'),
                'unit': 'kg',
                'stock': 60,
                'description': 'Sweet bite-sized cluster cherry tomatoes bursting with fresh summer nectar.',
                'image': 'products/images_3.jpg'
            },
        ]

        created_count = 0
        updated_count = 0

        for data in varieties:
            p, created = Product.objects.get_or_create(
                name=data['name'],
                defaults={
                    'farm': farm,
                    'category': data['category'],
                    'price': data['price'],
                    'unit': data['unit'],
                    'stock_quantity': data['stock'],
                    'description': data['description'],
                    'image': data['image'],
                    'is_active': True,
                    'is_approved': True,
                }
            )
            if created:
                created_count += 1
            else:
                p.price = data['price']
                p.unit = data['unit']
                p.stock_quantity = data['stock']
                p.is_active = True
                p.is_approved = True
                if not p.image:
                    p.image = data['image']
                p.save()
                updated_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'Done! Created {created_count} varieties, updated {updated_count} existing products.'
        ))
