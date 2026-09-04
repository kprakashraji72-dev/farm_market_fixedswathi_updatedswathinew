from django.conf import settings
from django.db import models


class DriverLocation(models.Model):
    driver = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='location',
        limit_choices_to={'role': 'driver'}
    )
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    accuracy_metres = models.FloatField(null=True, blank=True)
    heading = models.FloatField(null=True, blank=True, help_text='Direction of travel in degrees (0-360)')
    speed = models.FloatField(null=True, blank=True, help_text='Speed in metres/second')
    is_online = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.driver.username} @ ({self.latitude}, {self.longitude})'


class DeliveryLocationLog(models.Model):
    """
    Stores historical GPS breadcrumbs during active order deliveries,
    allowing route tracing and delivery audit records.
    """
    order = models.ForeignKey(
        'orders.Order', on_delete=models.CASCADE, related_name='location_logs',
        null=True, blank=True
    )
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='delivery_logs',
        limit_choices_to={'role': 'driver'}
    )
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    accuracy_metres = models.FloatField(null=True, blank=True)
    heading = models.FloatField(null=True, blank=True)
    speed = models.FloatField(null=True, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-recorded_at']
        indexes = [
            models.Index(fields=['order', '-recorded_at']),
            models.Index(fields=['driver', '-recorded_at']),
        ]

    def __str__(self):
        return f'Log for Driver {self.driver.username} on Order #{self.order_id if self.order else "N/A"} @ {self.recorded_at}'

