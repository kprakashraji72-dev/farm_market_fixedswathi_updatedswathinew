"""
Inventory models: Category, Farm (+ gallery images), Product.
Every Product belongs to exactly one Farm (per project requirement).
"""
from django.db import models
from django.utils.text import slugify
from django.utils import timezone
from django.conf import settings
from django.urls import reverse

# Shared filters for what's visible to customers: a farm/product is only
# "live" when it has no owner (admin-managed demo data) or its owning
# farmer has been admin-verified. Two constants because the field path
# differs depending on which model you're filtering.
LIVE_FARM_Q = models.Q(owner__isnull=True) | models.Q(owner__is_verified=True)          # for Farm querysets
LIVE_PRODUCT_FARM_Q = models.Q(farm__owner__isnull=True) | models.Q(farm__owner__is_verified=True)  # for Product querysets

# A product must also be admin-approved to be customer-visible — combine
# with LIVE_PRODUCT_FARM_Q and is_active=True wherever products are shown
# on the storefront (see store/inventory/orders views).
LIVE_APPROVED_PRODUCT_Q = LIVE_PRODUCT_FARM_Q & models.Q(is_approved=True)


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    icon = models.CharField(max_length=50, blank=True, help_text='FontAwesome class, e.g. fa-carrot')

    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Farm(models.Model):
    """A farm that supplies products. Optionally owned/managed by a FARMER-role user."""
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='farms', limit_choices_to={'role': 'farmer'}
    )
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, unique=True, blank=True)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=200, blank=True, help_text='City/region shown on the farm page')
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, help_text='Farm/Store GPS Latitude for pickup routing')
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, help_text='Farm/Store GPS Longitude for pickup routing')
    cover_image = models.ImageField(upload_to='farms/', blank=True, null=True)
    video_url = models.URLField(
        blank=True,
        help_text='Full URL to a farm video (e.g. YouTube embed URL), shown on the Farm Details page.'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('inventory:farm_detail', kwargs={'slug': self.slug})


class FarmImage(models.Model):
    """Extra gallery images for a farm's detail page."""
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='gallery_images')
    image = models.ImageField(upload_to='farms/')
    caption = models.CharField(max_length=150, blank=True)

    def __str__(self):
        return f'{self.farm.name} image'


class Product(models.Model):
    UNIT_CHOICES = [
        ('kg', 'Kilogram'), ('g', 'Gram'), ('lb', 'Pound'),
        ('dozen', 'Dozen'), ('piece', 'Piece'), ('litre', 'Litre'), ('bunch', 'Bunch'),
    ]

    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='products')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='products')
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, unique=True, blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES, default='kg')
    stock_quantity = models.PositiveIntegerField(default=0)
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    cost_price = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text='What this product costs you per unit. Optional — used to show profit on the farm report.'
    )
    bulk_quantity = models.PositiveIntegerField(
        default=1,
        help_text='For farmer-added products: the number of units the price/cost above was quoted for '
                   '(e.g. 22, if you are quoting your price for a lot of 22 pieces). Leave as 1 if the '
                   'price above is already for a single unit.'
    )
    hidden_by_farmer = models.BooleanField(
        default=False,
        help_text="Farmer removed this from THEIR OWN product list only (dashboard.views."
                  "farmer_product_delete). Purely cosmetic on the farmer side — it never touches "
                  "is_active, so it has zero effect on the admin Inventory page, the customer store, "
                  "or any existing/future OrderItem rows. Distinct from is_active, which is the flag "
                  "that actually controls customer-facing visibility."
    )

    hidden_by_farmer = models.BooleanField(
        default=False,
        help_text="Farmer removed this from THEIR OWN product list only (dashboard.views."
                  "farmer_product_delete). Purely cosmetic on the farmer side — it never touches "
                  "is_active, so it has zero effect on the admin Inventory page, the customer store, "
                  "or any existing/future OrderItem rows. Distinct from is_active, which is the flag "
                  "that actually controls customer-facing visibility."
    )

    # Approval workflow: a product added by a FARMER is never shown to
    # customers until an admin approves it. Products added directly by an
    # admin (dashboard:inventory_products) are auto-approved — see
    # dashboard.views.inventory_products / farmer_products.
    is_approved = models.BooleanField(
        default=True,
        help_text='Must be True for the product to appear on the customer-facing store. '
                   'Farmer-added products start False until an admin approves them.'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_products', limit_choices_to={'role': 'admin'}
    )

    # Rejection: distinct from just "not yet approved" (pending). Set when
    # an admin explicitly declines a farmer-added product — see
    # dashboard.views.product_reject. rejected_at not null is what moves a
    # product out of the "pending approval" queue/count on the admin
    # Inventory page and shows the farmer why it wasn't approved.
    # Approving a product (product_toggle_approved) always clears these.
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=255, blank=True)

    # Farm-to-Table Freshness tracking
    harvest_date = models.DateField(
        null=True, blank=True,
        help_text='When this batch was harvested from the farm fields.'
    )
    received_date = models.DateField(
        null=True, blank=True,
        help_text='When this product arrived at our store / inventory warehouse.'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while Product.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base_slug}-{counter}'
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('inventory:product_detail', kwargs={'slug': self.slug})

    @property
    def has_variants(self):
        return self.variants.filter(is_active=True).exists()

    @property
    def in_stock(self):
        """Whether this product can currently be bought. For variant products,
        this checks whether ANY active variant still has stock."""
        if self.has_variants:
            return self.variants.filter(is_active=True, stock_quantity__gt=0).exists()
        return self.stock_quantity > 0

    @property
    def farmer_unit_cost(self):
        """Per-single-unit cost worked out from the farmer's quoted cost_price
        and bulk_quantity — e.g. cost_price=1, bulk_quantity=22 -> 0.045/unit.
        A reference figure shown to admins when they set the customer-facing
        price at approval time (see dashboard.views.product_toggle_approved)."""
        if self.cost_price is None:
            return None
        qty = self.bulk_quantity or 1
        return self.cost_price / qty

    @property
    def display_price(self):
        """The price to show in listings: the base price, or — for variant
        products — the cheapest active variant's price."""
        if self.has_variants:
            cheapest = self.variants.filter(is_active=True).order_by('price').first()
            return cheapest.price if cheapest else self.price
        return self.price

    @property
    def display_unit(self):
        """The unit/weight to show in listings (e.g. '500g', 'kg')."""
        if self.has_variants:
            cheapest = self.variants.filter(is_active=True).order_by('price').first()
            if cheapest and cheapest.label:
                return cheapest.label
        return self.unit or 'kg'

    @property
    def effective_received_date(self):
        """Returns received_date, or falls back to created_at date."""
        if self.received_date:
            return self.received_date
        if self.created_at:
            return self.created_at.date()
        return timezone.now().date()

    @property
    def effective_harvest_date(self):
        """Returns harvest_date, or defaults to received_date / created_at date."""
        if self.harvest_date:
            return self.harvest_date
        return self.effective_received_date

    @property
    def days_in_store(self):
        """Number of days this product has been in the store since arrival."""
        ref = self.effective_received_date
        if ref:
            delta = (timezone.now().date() - ref).days
            return max(0, delta)
        return 0

    @property
    def days_since_harvest(self):
        """Number of days since field harvest."""
        ref = self.effective_harvest_date
        if ref:
            delta = (timezone.now().date() - ref).days
            return max(0, delta)
        return 0

    @property
    def freshness_badge(self):
        """Display badge for product freshness based on days in store."""
        if not self.in_stock:
            return {'label': 'Sold Out', 'color': 'secondary', 'subtext': 'Awaiting Next Fresh Batch'}
        days = self.days_in_store
        if days == 0:
            return {'label': 'Arrived Today', 'color': 'success', 'subtext': 'Peak Garden Freshness'}
        elif days <= 2:
            return {'label': f'{days} Day{"s" if days > 1 else ""} Fresh', 'color': 'success', 'subtext': 'Peak Freshness'}
        elif days <= 4:
            return {'label': f'{days} Days in Store', 'color': 'info', 'subtext': 'Store Fresh'}
        else:
            return {'label': f'{days} Days in Store', 'color': 'warning', 'subtext': 'Standard Freshness'}


class ProductVariant(models.Model):
    """
    A purchasable size/weight option for a product — e.g. a "Tomatoes"
    product might have variants "400g" ($2.00), "1kg" ($4.50), "2kg" ($8.00),
    each with its own price and its own stock count.

    Products with variants are sold by variant only (the base
    Product.price/unit/stock_quantity are ignored on the storefront once
    at least one active variant exists) — see Product.has_variants.
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    label = models.CharField(max_length=30, help_text='e.g. "400g", "1kg", "2kg", "500ml"')
    price = models.DecimalField(max_digits=8, decimal_places=2)
    stock_quantity = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0, help_text='Lower numbers show first (e.g. 400g before 1kg).')

    class Meta:
        ordering = ['sort_order', 'price']

    def __str__(self):
        return f'{self.product.name} — {self.label}'

    @property
    def in_stock(self):
        return self.stock_quantity > 0

    @property
    def cart_key(self):
        return f'v{self.pk}'


class ProductDamage(models.Model):
    """
    A logged loss of stock reported against one of a farm's products
    (spoiled/damaged in transit or storage) — feeds the farm's monthly
    product report so damage is tracked separately from sold stock.

    Filed by in-store Employees with the 'can_report_damage' permission
    (dashboard.views.employee_report_damage): audits ANY product in the
    catalogue, but the report sits PENDING and stock is left untouched
    until an admin reviews it (dashboard.views.damage_review /
    damage_approve / damage_reject). Stock is only deducted at the moment
    of approval. (Farmers previously had a self-service damage report too;
    that was removed from the Farmer Products page.)
    """
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending review'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='damages')
    quantity = models.PositiveIntegerField()
    note = models.CharField(max_length=255, blank=True, help_text='Optional reason, e.g. "spoiled in transit".')
    reported_at = models.DateTimeField(auto_now_add=True)

    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='damage_reports', help_text='Farmer or employee who filed this report.'
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.APPROVED,
        help_text='Farmer self-reports are auto-approved. Employee reports start Pending '
                   'and only affect stock once an admin approves them.'
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='damage_reviews', limit_choices_to={'role': 'admin'}
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-reported_at']

    def __str__(self):
        return f'{self.quantity} {self.product.unit} damaged — {self.product.name}'