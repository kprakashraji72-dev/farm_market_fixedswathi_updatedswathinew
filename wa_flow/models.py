"""
wa_flow/models.py
─────────────────
Data models for WhatsApp Flow produce ordering:
- Category (slug id like "cat_veg", title)
- Product (slug id like "prod_16", title, category FK, unit_price, unit_label)
- Quantity (fixed mapping: qty_1, qty_2, qty_3, qty_5)
- Order (product FK, quantity_label, unit_price, subtotal, delivery_fee=5,
         total_amount, customer_name, delivery_phone, delivery_address,
         payment_mode COD/UPI, status, created_at)
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List

from django.db import models


class Category(models.Model):
    id = models.CharField(max_length=50, primary_key=True)  # slug like "cat_veg"
    title = models.CharField(max_length=100)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ["title"]

    def __str__(self) -> str:
        return self.title


class Product(models.Model):
    id = models.CharField(max_length=50, primary_key=True)  # slug like "prod_16"
    title = models.CharField(max_length=150)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="products")
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)
    unit_label = models.CharField(max_length=20, default="kg")

    class Meta:
        ordering = ["title"]

    def __str__(self) -> str:
        return f"{self.title} (₹{self.unit_price}/{self.unit_label})"

    @property
    def display_title(self) -> str:
        """Formatted as '{name} (₹{price}/kg)' per flow.json spec."""
        return f"{self.title} (₹{self.unit_price:.0f}/{self.unit_label})"


# Fixed quantity options stored as simple mapping (not DB table)
QUANTITY_CHOICES: List[Dict[str, Any]] = [
    {"id": "qty_1", "title": "1 kg (or bunch)", "multiplier": 1},
    {"id": "qty_2", "title": "2 kg", "multiplier": 2},
    {"id": "qty_3", "title": "3 kg", "multiplier": 3},
    {"id": "qty_5", "title": "5 kg (Family Pack)", "multiplier": 5},
]

QUANTITY_MAP: Dict[str, Dict[str, Any]] = {q["id"]: q for q in QUANTITY_CHOICES}


class Order(models.Model):
    class PaymentMode(models.TextChoices):
        COD = "COD", "Cash on Delivery (COD)"
        UPI = "UPI", "UPI on Delivery"

    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="flow_orders"
    )
    quantity_label = models.CharField(max_length=50)
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)
    subtotal = models.DecimalField(max_digits=8, decimal_places=2)
    delivery_fee = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("5.00"))
    total_amount = models.DecimalField(max_digits=8, decimal_places=2)
    customer_name = models.CharField(max_length=150)
    delivery_phone = models.CharField(max_length=20)
    delivery_address = models.TextField()
    payment_mode = models.CharField(
        max_length=10,
        choices=PaymentMode.choices,
        default=PaymentMode.COD
    )
    status = models.CharField(max_length=30, default="CONFIRMED")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Order #{self.pk} - {self.customer_name} (₹{self.total_amount})"
