from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, DriverKYC, FarmerKYC


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    """Exposes role & profile fields in Django's built-in admin."""
    list_display = ('username', 'email', 'role', 'is_verified', 'is_active', 'date_joined')
    list_filter = ('role', 'is_verified', 'is_active')
    search_fields = ('username', 'email', 'phone_number')

    fieldsets = UserAdmin.fieldsets + (
        ('Fresh Trace Profile', {
            'fields': ('role', 'phone_number', 'address', 'profile_image', 'is_verified')
        }),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Fresh Trace Profile', {
            'fields': ('role', 'is_verified')
        }),
    )


@admin.register(DriverKYC)
class DriverKYCAdmin(admin.ModelAdmin):
    list_display = ('user', 'license_number', 'vehicle_number', 'renewal_due_date', 'submitted_at')
    search_fields = ('user__username', 'license_number', 'aadhar_number', 'vehicle_number')


@admin.register(FarmerKYC)
class FarmerKYCAdmin(admin.ModelAdmin):
    list_display = ('user', 'iso_certificate_number', 'iso_expiry_date', 'submitted_at')
    search_fields = ('user__username', 'iso_certificate_number')
