"""
Accounts models: a single custom User model that carries a `role` field.
Using one model with a role (instead of separate Customer/Driver/Admin
models) keeps Django's built-in auth, permissions, and admin working
out-of-the-box while still letting us branch behaviour by role.
"""
from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from .validators import validate_kyc_document


class FreshTraceUserManager(UserManager):
    """
    Same as Django's default UserManager, except create_superuser also
    sets role='admin' and is_verified=True. Without this, `manage.py
    createsuperuser` only sets is_staff/is_superuser — the app's own
    `role` field (which the dashboard actually checks) would stay at
    its default 'customer', and the new superuser couldn't reach
    /dashboard/ until someone manually fixed it in the shell.
    """
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('role', User.Role.ADMIN)
        extra_fields.setdefault('is_verified', True)
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    """
    Extends Django's AbstractUser with the fields Fresh Trace needs:
    a role (for redirect logic & permissions), contact info, and a
    profile photo. AUTH_USER_MODEL points here (see settings.py).
    """

    class Role(models.TextChoices):
        ADMIN = 'admin', 'Admin'
        CUSTOMER = 'customer', 'Customer'
        DRIVER = 'driver', 'Driver'
        FARMER = 'farmer', 'Farmer'
        EMPLOYEE = 'employee', 'Employee'
        SUPPORT_STAFF = 'support_staff', 'Support Staff'

    objects = FreshTraceUserManager()

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CUSTOMER,
        help_text='Determines dashboard access and post-login redirect.',
    )
    phone_number = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    profile_image = models.ImageField(
        upload_to='users/', blank=True, null=True,
        help_text='Shown on profile page and navbar avatar.'
    )
    is_verified = models.BooleanField(
        default=False,
        help_text='Admin can mark drivers/farmers verified before they can operate.'
    )
    last_order_assigned_at = models.DateTimeField(
        null=True, blank=True,
        help_text='Drivers only — when they last received an order. Used for '
                   'first-in-first-out dispatch: whoever has waited longest gets the next order.'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.username} ({self.get_role_display()})'

    # --- Convenience helpers used across the project ---
    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN

    @property
    def is_customer_role(self):
        return self.role == self.Role.CUSTOMER

    @property
    def is_driver_role(self):
        return self.role == self.Role.DRIVER

    @property
    def is_farmer_role(self):
        return self.role == self.Role.FARMER

    @property
    def is_employee_role(self):
        return self.role == self.Role.EMPLOYEE

    @property
    def is_support_staff_role(self):
        return self.role == self.Role.SUPPORT_STAFF

    def get_dashboard_url_name(self):
        """Returns the URL name to redirect to right after login, per role."""
        mapping = {
            self.Role.ADMIN: 'dashboard:home',
            self.Role.DRIVER: 'tracking:driver_dashboard',
            self.Role.FARMER: 'dashboard:farmer_home',
            self.Role.EMPLOYEE: 'dashboard:home',
            self.Role.SUPPORT_STAFF: 'customer_support:console',
            self.Role.CUSTOMER: 'store:home',
        }
        return mapping.get(self.role, 'store:home')

    def has_employee_permission(self, perm):
        """perm is one of 'can_manage_orders', 'can_manage_inventory', 'can_view_reports'.
        Admins implicitly have every permission; employees only what's granted on
        their EmployeePermission row; everyone else has none."""
        if self.is_admin_role:
            return True
        if not self.is_employee_role:
            return False
        profile = getattr(self, 'employee_permission', None)
        return bool(profile and getattr(profile, perm, False))


class DriverKYC(models.Model):
    """
    KYC / compliance documents a delivery partner (driver) must submit
    before an admin can verify them. One row per driver, created at
    driver self-registration and editable later from the driver's own
    'My Documents' page.
    """
    user = models.OneToOneField(
        'accounts.User', on_delete=models.CASCADE, related_name='driver_kyc',
        limit_choices_to={'role': 'driver'},
    )

    # Identity & Date of Birth
    date_of_birth = models.DateField(
        null=True, blank=True,
        help_text='Date of birth of the driver (must be at least 18 years old).'
    )
    aadhar_number = models.CharField(
        max_length=12, help_text='12-digit Aadhar number (digits only).'
    )
    aadhar_document = models.FileField(
        upload_to='users/driver_kyc/aadhar/',
        validators=[validate_kyc_document],
        help_text='Scan/photo of the Aadhar card (PDF, JPG or PNG, max 5 MB).'
    )

    # Driving license
    license_number = models.CharField(max_length=30)
    license_document = models.FileField(
        upload_to='users/driver_kyc/license/',
        validators=[validate_kyc_document],
        help_text="Scan/photo of the driving license (PDF, JPG or PNG, max 5 MB)."
    )
    license_expiry_date = models.DateField(
        null=True, blank=True, help_text='Date the driving license itself expires.'
    )

    # Vehicle
    vehicle_number = models.CharField(max_length=20, help_text='Registration number, e.g. TN09AB1234.')
    vehicle_document = models.FileField(
        upload_to='users/driver_kyc/vehicle/',
        blank=True, null=True,
        validators=[validate_kyc_document],
        help_text='RC book / vehicle registration certificate (PDF, JPG or PNG, max 5 MB; optional).'
    )

    # Renewal tracking — how much the renewal (license/RC/insurance) costs
    # and when it is next due, so admins can see who needs to renew soon.
    renewal_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Amount generated/paid for the last license or vehicle renewal.'
    )
    renewal_due_date = models.DateField(
        null=True, blank=True, help_text='Next renewal due date for license/vehicle documents.'
    )

    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Driver KYC'
        verbose_name_plural = 'Driver KYC records'

    def __str__(self):
        return f'KYC for {self.user.username}'

    @property
    def age(self):
        """Calculates current age from date_of_birth in full years."""
        if not self.date_of_birth:
            return None
        from django.utils import timezone
        today = timezone.now().date()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )

    @property
    def is_renewal_due_soon(self):
        if not self.renewal_due_date:
            return False
        from django.utils import timezone
        return (self.renewal_due_date - timezone.now().date()).days <= 30


class FarmerKYC(models.Model):
    """
    Compliance record for a farmer/seller partner — currently the ISO
    (or equivalent food-safety/organic) certificate required before an
    admin verifies the farmer and lets their farm go live.
    """
    user = models.OneToOneField(
        'accounts.User', on_delete=models.CASCADE, related_name='farmer_kyc',
        limit_choices_to={'role': 'farmer'},
    )

    iso_certificate_number = models.CharField(max_length=60, blank=True)
    iso_certificate_document = models.FileField(
        upload_to='users/farmer_kyc/iso_certificate/',
        validators=[validate_kyc_document],
        help_text='ISO / organic / food-safety certificate (PDF, JPG or PNG, max 5 MB).'
    )
    iso_issue_date = models.DateField(null=True, blank=True)
    iso_expiry_date = models.DateField(null=True, blank=True)

    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Farmer KYC'
        verbose_name_plural = 'Farmer KYC records'

    def __str__(self):
        return f'ISO cert for {self.user.username}'

    @property
    def is_expiring_soon(self):
        if not self.iso_expiry_date:
            return False
        from django.utils import timezone
        return (self.iso_expiry_date - timezone.now().date()).days <= 30


class EmployeePermission(models.Model):
    """
    Access-control record for a role == EMPLOYEE user (in-store staff,
    not farm-side). An admin ticks which areas of the dashboard that
    employee can reach — see accounts.decorators.dashboard_access_required
    and User.has_employee_permission. Everything defaults to no access,
    so a brand-new employee account can't touch anything until an admin
    explicitly grants it on the Role Management page.
    """
    user = models.OneToOneField(
        'accounts.User', on_delete=models.CASCADE, related_name='employee_permission',
        limit_choices_to={'role': 'employee'},
    )
    can_manage_orders = models.BooleanField(
        default=False, help_text='View/update order status, assign drivers.'
    )
    can_manage_inventory = models.BooleanField(
        default=False, help_text='Manage store products & categories (not farm profiles or farmer verification).'
    )
    can_view_reports = models.BooleanField(
        default=False, help_text='View the sales/inventory reports page (read-only).'
    )
    can_report_damage = models.BooleanField(
        default=False, help_text='Audit store products and report damaged/spoiled stock for admin review.'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Employee permission'
        verbose_name_plural = 'Employee permissions'

    def __str__(self):
        return f'Permissions for {self.user.username}'
