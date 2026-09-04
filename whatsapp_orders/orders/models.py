"""
orders/models.py
────────────────
Data models powering the WhatsApp Flow ('Farm Fresh Produce') ordering backend.
Models:
1. Category
2. Product
3. FlowSession
4. Order
"""

import uuid
from decimal import Decimal
from django.db import models


class Category(models.Model):
    """
    Produce Category (e.g., 'Fresh Vegetables', 'Farm Fresh Fruits', 'Organic Greens').
    Can use custom id (e.g., 'cat_veg') or autoincrement integer.
    """
    id = models.CharField(max_length=50, primary_key=True)
    name = models.CharField(max_length=100)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Product(models.Model):
    """
    Farm Fresh Produce product item under a category.
    """
    id = models.CharField(max_length=50, primary_key=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="products")
    name = models.CharField(max_length=150)
    unit_rate = models.DecimalField(max_digits=10, decimal_places=2)
    unit_label = models.CharField(max_length=50, default="1 kg (or bunch)")

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} (₹{self.unit_rate:.2f}/{self.unit_label})"

    @property
    def dropdown_title(self) -> str:
        """Formatted title for WhatsApp Flow dropdowns, e.g. 'Ooty Red Carrot (₹80/kg)'."""
        return f"{self.name} (₹{self.unit_rate:.0f}/kg)"


class FlowSession(models.Model):
    """
    Tracks customer WhatsApp Flow state across screens:
    PRODUCTS -> DELIVERY -> SUMMARY -> COMPLETE
    """
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        DELIVERY = "delivery", "Delivery"
        SUMMARY = "summary", "Summary"
        COMPLETE = "complete", "Complete"

    flow_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    customer_phone = models.CharField(max_length=25, db_index=True)
    current_screen = models.CharField(max_length=50, default="PRODUCTS")

    selected_category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="sessions"
    )
    selected_product = models.ForeignKey(
        Product, on_delete=models.SET_NULL, null=True, blank=True, related_name="sessions"
    )
    selected_quantity = models.CharField(max_length=50, default="1 kg (or bunch)")
    total_payable = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    full_name = models.CharField(max_length=150, blank=True)
    phone_number = models.CharField(max_length=25, blank=True)
    delivery_address = models.TextField(blank=True, null=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"Session {self.flow_token} ({self.customer_phone}) [{self.status}]"


class Order(models.Model):
    """
    Order record created when the customer completes the WhatsApp Flow.
    """
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        DELIVERED = "delivered", "Delivered"

    session = models.OneToOneField(
        FlowSession, on_delete=models.CASCADE, related_name="order"
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="orders"
    )
    quantity = models.CharField(max_length=50)
    unit_rate = models.DecimalField(max_digits=10, decimal_places=2)
    total_payable = models.DecimalField(max_digits=10, decimal_places=2)

    customer_name = models.CharField(max_length=150)
    customer_phone = models.CharField(max_length=25, db_index=True)
    delivery_address = models.TextField(blank=True, null=True)

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.CONFIRMED
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Order #{self.pk} - {self.customer_name} ({self.product.name} - ₹{self.total_payable})"
