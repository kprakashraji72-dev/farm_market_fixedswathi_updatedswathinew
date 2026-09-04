from django.contrib import admin
from django.utils import timezone
from .models import SupportTicket, TicketReply


class TicketReplyInline(admin.TabularInline):
    model = TicketReply
    extra = 1
    readonly_fields = ('created_at',)
    fields = ('sender', 'message', 'is_staff_reply', 'created_at')


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ('id', 'subject', 'user', 'category', 'status', 'assigned_to', 'order', 'created_at', 'resolved_at')
    list_filter = ('status', 'category', 'assigned_to', 'created_at')
    search_fields = ('subject', 'message', 'user__username', 'user__email', 'admin_response')
    list_editable = ('status', 'assigned_to')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [TicketReplyInline]

    fieldsets = (
        ('Ticket Information', {
            'fields': ('user', 'order', 'category', 'subject', 'message', 'created_at', 'updated_at')
        }),
        ('Staff Assignment & Status', {
            'fields': ('assigned_to', 'status', 'resolved_at')
        }),
    )

    def save_model(self, request, obj, form, change):
        if obj.status in ['resolved', 'closed'] and not obj.resolved_at:
            obj.resolved_at = timezone.now()
        elif obj.status in ['open', 'in_progress']:
            obj.resolved_at = None
        super().save_model(request, obj, form, change)


@admin.register(TicketReply)
class TicketReplyAdmin(admin.ModelAdmin):
    list_display = ('id', 'ticket', 'sender', 'is_staff_reply', 'created_at')
    list_filter = ('is_staff_reply', 'created_at')
    search_fields = ('message', 'sender__username', 'ticket__subject')
