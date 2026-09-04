"""
wa_flow/migrations/0002_seed_flow_products.py
─────────────────────────────────────────────
Data migration to seed categories and initial products for Fresh Trace Farm Market.
"""

from decimal import Decimal
from django.db import migrations


def seed_categories_and_products(apps, schema_editor):
    Category = apps.get_model("wa_flow", "Category")
    Product = apps.get_model("wa_flow", "Product")

    categories_data = [
        {"id": "cat_veg", "title": "🥕 Fresh Vegetables"},
        {"id": "cat_fruits", "title": "🍎 Farm Fresh Fruits"},
        {"id": "cat_greens", "title": "🥬 Organic Greens"},
    ]

    for cat in categories_data:
        Category.objects.update_or_create(id=cat["id"], defaults={"title": cat["title"]})

    cat_veg = Category.objects.get(id="cat_veg")
    cat_fruits = Category.objects.get(id="cat_fruits")
    cat_greens = Category.objects.get(id="cat_greens")

    products_data = [
        # Vegetables
        {"id": "prod_16", "title": "Ooty Red Carrot", "category": cat_veg, "unit_price": Decimal("80.00"), "unit_label": "kg"},
        {"id": "prod_29", "title": "Fresh Orange Carrot", "category": cat_veg, "unit_price": Decimal("75.00"), "unit_label": "kg"},
        {"id": "prod_15", "title": "Regular Carrot", "category": cat_veg, "unit_price": Decimal("70.00"), "unit_label": "kg"},
        {"id": "prod_34", "title": "Organic Tomatoes", "category": cat_veg, "unit_price": Decimal("40.00"), "unit_label": "kg"},
        {"id": "prod_21", "title": "Farm Fresh Potato", "category": cat_veg, "unit_price": Decimal("40.00"), "unit_label": "kg"},
        {"id": "prod_19", "title": "Beetroot", "category": cat_veg, "unit_price": Decimal("45.00"), "unit_label": "kg"},
        # Fruits
        {"id": "prod_fruits_1", "title": "Shimla Apple", "category": cat_fruits, "unit_price": Decimal("120.00"), "unit_label": "kg"},
        {"id": "prod_fruits_2", "title": "Robusta Banana", "category": cat_fruits, "unit_price": Decimal("50.00"), "unit_label": "kg"},
        # Greens
        {"id": "prod_greens_1", "title": "Fresh Palak / Spinach", "category": cat_greens, "unit_price": Decimal("30.00"), "unit_label": "bunch"},
        {"id": "prod_greens_2", "title": "Coriander & Mint Pack", "category": cat_greens, "unit_price": Decimal("25.00"), "unit_label": "bunch"},
    ]

    for prod in products_data:
        Product.objects.update_or_create(
            id=prod["id"],
            defaults={
                "title": prod["title"],
                "category": prod["category"],
                "unit_price": prod["unit_price"],
                "unit_label": prod["unit_label"],
            }
        )


def rollback_seed(apps, schema_editor):
    Category = apps.get_model("wa_flow", "Category")
    Product = apps.get_model("wa_flow", "Product")
    Product.objects.all().delete()
    Category.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("wa_flow", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_categories_and_products, rollback_seed),
    ]
