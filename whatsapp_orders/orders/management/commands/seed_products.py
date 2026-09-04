"""
orders/management/commands/seed_products.py
───────────────────────────────────────────
Seeds initial Categories and Products in the whatsapp_orders database.
Can be executed via:
    python manage.py seed_products
"""

from decimal import Decimal
from django.core.management.base import BaseCommand
from orders.models import Category, Product


class Command(BaseCommand):
    help = "Populates initial Categories and Products for the WhatsApp Flow ordering experience."

    def handle(self, *args, **options):
        self.stdout.write("Seeding Categories & Products...")

        # Categories
        veg, _ = Category.objects.get_or_create(id="cat_veg", defaults={"name": "🥕 Fresh Vegetables"})
        fruits, _ = Category.objects.get_or_create(id="cat_fruits", defaults={"name": "🍎 Farm Fresh Fruits"})
        greens, _ = Category.objects.get_or_create(id="cat_greens", defaults={"name": "🥬 Organic Greens"})

        # Products
        products_data = [
            # Fresh Vegetables
            {"id": "prod_16", "category": veg, "name": "Ooty Red Carrot", "unit_rate": Decimal("80.00"), "unit_label": "1 kg (or bunch)"},
            {"id": "prod_29", "category": veg, "name": "Fresh Orange Carrot", "unit_rate": Decimal("75.00"), "unit_label": "1 kg (or bunch)"},
            {"id": "prod_15", "category": veg, "name": "Regular Carrot", "unit_rate": Decimal("70.00"), "unit_label": "1 kg (or bunch)"},
            {"id": "prod_34", "category": veg, "name": "Organic Tomatoes", "unit_rate": Decimal("40.00"), "unit_label": "1 kg (or bunch)"},
            {"id": "prod_21", "category": veg, "name": "Farm Fresh Potato", "unit_rate": Decimal("40.00"), "unit_label": "1 kg (or bunch)"},
            {"id": "prod_19", "category": veg, "name": "Beetroot", "unit_rate": Decimal("45.00"), "unit_label": "1 kg (or bunch)"},

            # Farm Fresh Fruits
            {"id": "prod_apple", "category": fruits, "name": "Shimla Apple", "unit_rate": Decimal("120.00"), "unit_label": "1 kg (or bunch)"},
            {"id": "prod_banana", "category": fruits, "name": "Robusta Banana", "unit_rate": Decimal("50.00"), "unit_label": "1 kg (or bunch)"},

            # Organic Greens
            {"id": "prod_palak", "category": greens, "name": "Fresh Palak / Spinach", "unit_rate": Decimal("30.00"), "unit_label": "1 kg (or bunch)"},
            {"id": "prod_coriander", "category": greens, "name": "Coriander & Mint Pack", "unit_rate": Decimal("25.00"), "unit_label": "1 kg (or bunch)"},
        ]

        for p in products_data:
            prod, created = Product.objects.update_or_create(
                id=p["id"],
                defaults={
                    "category": p["category"],
                    "name": p["name"],
                    "unit_rate": p["unit_rate"],
                    "unit_label": p["unit_label"],
                }
            )
            action = "Created" if created else "Updated"
            safe_name = prod.name.encode("ascii", "replace").decode("ascii")
            self.stdout.write(f"[{action}] {safe_name} (Rs.{prod.unit_rate}/{prod.unit_label})")

        self.stdout.write(self.style.SUCCESS("\nDatabase seeding complete!"))
