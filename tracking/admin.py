from django.contrib import admin
from .models import DriverLocation


@admin.register(DriverLocation)
class DriverLocationAdmin(admin.ModelAdmin):
    list_display = ('driver', 'latitude', 'longitude', 'is_online', 'updated_at')
