from datetime import timedelta
from django.db import models
from django.utils import timezone


class WhatsAppFollowUp(models.Model):
    """
    Tracks outgoing interactive WhatsApp messages sent to customers,
    detects if the customer replies via webhook, and manages automated/manual
    follow-up reminder template dispatches.
    """
    customer_name = models.CharField(max_length=255, blank=True, default='')
    phone_number = models.CharField(max_length=32, db_index=True)
    interactive_message_sent_at = models.DateTimeField(default=timezone.now, db_index=True)
    
    # Reply tracking (updated automatically by incoming webhook event)
    customer_replied = models.BooleanField(default=False, db_index=True)
    customer_replied_at = models.DateTimeField(null=True, blank=True)
    last_reply_text = models.TextField(null=True, blank=True)

    # 12-hour follow-up template tracking
    followup_template_sent = models.BooleanField(default=False, db_index=True)
    followup_template_sent_at = models.DateTimeField(null=True, blank=True)

    # Link to related customer order if available
    related_order = models.ForeignKey(
        'orders.Order',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='whatsapp_followups'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-interactive_message_sent_at']
        verbose_name = 'WhatsApp Follow-Up'
        verbose_name_plural = 'WhatsApp Follow-Ups'

    def __str__(self):
        name = self.customer_name or self.phone_number
        return f"Follow-up for {name} ({self.phone_number})"

    @property
    def status_code(self):
        """
        Returns one of: 'replied', 'sent', 'pending'
        """
        if self.customer_replied:
            return 'replied'
        if self.followup_template_sent:
            return 'sent'
        return 'pending'

    @property
    def status_label(self):
        """
        Returns human-friendly status label:
        - 'Not needed — replied'
        - 'Sent ✓'
        - 'Not sent'
        """
        if self.customer_replied:
            return 'Not needed — replied'
        if self.followup_template_sent:
            return 'Sent ✓'
        return 'Not sent'

    @property
    def is_due_for_followup(self):
        """
        True if 12 hours have passed since interactive message was sent,
        the customer has NOT replied, and followup has NOT been sent yet.
        """
        if self.customer_replied or self.followup_template_sent:
            return False
        return self.interactive_message_sent_at <= timezone.now() - timedelta(hours=12)

    @property
    def hours_since_sent(self):
        """Returns elapsed hours since the interactive message was sent."""
        diff = timezone.now() - self.interactive_message_sent_at
        return max(0.0, diff.total_seconds() / 3600.0)
