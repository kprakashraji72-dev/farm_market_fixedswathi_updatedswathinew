from django.contrib import admin
from .models import WhatsAppFollowUp


@admin.register(WhatsAppFollowUp)
class WhatsAppFollowUpAdmin(admin.ModelAdmin):
    list_display = [
        'customer_name',
        'phone_number',
        'interactive_message_sent_at',
        'customer_replied',
        'customer_replied_at',
        'followup_template_sent',
        'followup_template_sent_at',
        'related_order',
    ]
    list_filter = ['customer_replied', 'followup_template_sent', 'interactive_message_sent_at']
    search_fields = ['customer_name', 'phone_number', 'related_order__id']
    readonly_fields = ['created_at', 'updated_at']
