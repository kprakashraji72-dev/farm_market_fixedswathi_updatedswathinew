"""
Order & OrderItem models. The Cart itself is session-based (see
orders/cart.py) rather than a DB model — it's simpler for anonymous-then-
login flows and matches the "AJAX cart, no page refresh" requirement.
Once checkout happens, the cart becomes a persisted Order.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from inventory.models import Product


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CONFIRMED = 'confirmed', 'Confirmed'
        OUT_FOR_DELIVERY = 'out_for_delivery', 'Out for Delivery'
        DELIVERED = 'delivered', 'Delivered'
        CANCELLED = 'cancelled', 'Cancelled'

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='orders'
    )
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='deliveries', limit_choices_to={'role': 'driver'}
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    delivery_address = models.TextField()
    delivery_phone = models.CharField(max_length=20)
    delivery_latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        help_text='Captured from the browser at checkout (if permission granted) so the nearest driver can be auto-assigned.'
    )
    delivery_longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('5.00'))
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    estimated_delivery_time = models.DateTimeField(null=True, blank=True)

    # Delivery-completion OTP: generated the moment a driver is assigned
    # (see orders.services.assign_driver). The customer sees this code on
    # their tracking page and reads it out to the driver at drop-off; the
    # driver types it in on their dashboard to mark the order Delivered.
    delivery_otp = models.CharField(max_length=6, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    arrived_at = models.DateTimeField(
        null=True, blank=True,
        help_text='When the driver confirmed reaching the customer location. The OTP is only generated at this point.'
    )
    otp_verified_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Order #{self.pk} — {self.customer.username}'

    def recalculate_total(self):
        self.subtotal = sum(item.line_total for item in self.items.all())
        self.total_amount = self.subtotal + self.delivery_fee
        self.save(update_fields=['subtotal', 'total_amount'])

    @property
    def is_trackable(self):
        return self.status in (self.Status.CONFIRMED, self.Status.OUT_FOR_DELIVERY)

    @property
    def can_be_cancelled(self):
        """Customer self-service cancel is only allowed before a driver picks it up."""
        return self.status in (self.Status.PENDING, self.Status.CONFIRMED)

    @property
    def is_otp_visible(self):
        """Show the delivery OTP to the customer once a driver is assigned, until delivered."""
        return bool(self.delivery_otp) and self.is_trackable

    def generate_otp(self):
        """6-digit delivery-completion code. Called once, when a driver is assigned."""
        import random
        self.delivery_otp = f'{random.randint(0, 999999):06d}'
        return self.delivery_otp

    @property
    def pickup_farm(self):
        """Returns the primary farm associated with items in this order."""
        item = self.items.select_related('product__farm').first()
        if item and item.product and item.product.farm:
            return item.product.farm
        return None

    @property
    def pickup_farm_name(self):
        farm = self.pickup_farm
        if farm:
            return farm.name
        return 'Organic Farm Hub'

    @property
    def pickup_latitude(self):
        farm = self.pickup_farm
        if farm and farm.latitude:
            return float(farm.latitude)
        return None

    @property
    def pickup_longitude(self):
        farm = self.pickup_farm
        if farm and farm.longitude:
            return float(farm.longitude)
        return None



class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    variant = models.ForeignKey('inventory.ProductVariant', on_delete=models.SET_NULL, null=True, blank=True)
    product_name = models.CharField(max_length=150)  # snapshot, survives product deletion/price change
    variant_label = models.CharField(max_length=30, blank=True)  # e.g. "1kg" — snapshot, survives variant deletion
    price = models.DecimalField(max_digits=8, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        if self.variant_label:
            return f'{self.quantity} x {self.product_name} ({self.variant_label})'
        return f'{self.quantity} x {self.product_name}'

    @property
    def line_total(self):
        return self.price * self.quantity


class Cart(models.Model):
    """
    Shopping cart tied to session_key (for guests) and optionally to a logged-in User.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name='carts'
    )
    session_key = models.CharField(max_length=40, null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        if self.user:
            return f'Cart (User: {self.user.username})'
        return f'Cart (Session: {self.session_key})'

    @property
    def total_items(self):
        return sum(item.quantity for item in self.items.all())

    @property
    def total_price(self):
        return sum(item.total_price for item in self.items.all()) or Decimal('0.00')


class CartItem(models.Model):
    """
    Line item inside a Cart, linked to a specific ProductVariant and tracking quantity.
    """
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    variant = models.ForeignKey('inventory.ProductVariant', on_delete=models.CASCADE, related_name='cart_items')
    quantity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('cart', 'variant')
        ordering = ['created_at']

    def __str__(self):
        return f'{self.quantity} x {self.variant}'

    @property
    def total_price(self):
        return self.variant.price * self.quantity

