from django.conf import settings
from django.db import models
from orders.models import Order


class SupportTicket(models.Model):
    class Category(models.TextChoices):
        DELIVERY_ISSUE = 'delivery_issue', 'Delivery Issue'
        PAYMENT_ISSUE = 'payment_issue', 'Payment Issue'
        PRODUCT_QUALITY = 'product_quality', 'Product Quality / Freshness'
        ACCOUNT_ISSUE = 'account_issue', 'Account Issue'
        OTHER = 'other', 'Other Inquiries'

    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        IN_PROGRESS = 'in_progress', 'In Progress'
        RESOLVED = 'resolved', 'Resolved'
        CLOSED = 'closed', 'Closed'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='support_tickets'
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_support_tickets',
        help_text='Support staff member or admin assigned to handle this ticket.'
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='support_tickets',
        help_text='Optional order reference associated with this support ticket.'
    )
    subject = models.CharField(max_length=200)
    category = models.CharField(
        max_length=30,
        choices=Category.choices,
        default=Category.OTHER
    )
    message = models.TextField(help_text='Initial inquiry message from customer.')
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN
    )
    admin_response = models.TextField(
        blank=True,
        null=True,
        help_text='Legacy single response field.'
    )
    attachment = models.FileField(
        upload_to='support_attachments/',
        null=True,
        blank=True,
        help_text='Optional image or document attached to ticket inquiry.'
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Support Ticket'
        verbose_name_plural = 'Support Tickets'

    def __str__(self):
        return f"Ticket #{self.id}: {self.subject} ({self.get_status_display()})"

    @property
    def is_image(self):
        if not self.attachment:
            return False
        ext = self.attachment.name.lower().split('.')[-1]
        return ext in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp']

    @property
    def is_pdf(self):
        if not self.attachment:
            return False
        return self.attachment.name.lower().endswith('.pdf')

    @property
    def filename(self):
        if self.attachment:
            import os
            return os.path.basename(self.attachment.name)
        return ""

    @property
    def file_size_display(self):
        if self.attachment and hasattr(self.attachment, 'size'):
            try:
                size = self.attachment.size
                if size < 1024:
                    return f"{size} B"
                elif size < 1024 * 1024:
                    return f"{size / 1024:.1f} KB"
                else:
                    return f"{size / (1024 * 1024):.1f} MB"
            except Exception:
                pass
        return ""

    @property
    def file_icon(self):
        if not self.attachment:
            return "fa-file"
        ext = self.attachment.name.lower().split('.')[-1]
        if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp']:
            return "fa-file-image"
        elif ext == 'pdf':
            return "fa-file-pdf"
        elif ext in ['doc', 'docx']:
            return "fa-file-word"
        elif ext in ['xls', 'xlsx', 'csv']:
            return "fa-file-excel"
        elif ext in ['zip', 'rar', 'tar', 'gz']:
            return "fa-file-zipper"
        return "fa-file-lines"


class TicketReply(models.Model):
    ticket = models.ForeignKey(
        SupportTicket,
        on_delete=models.CASCADE,
        related_name='replies'
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ticket_replies'
    )
    message = models.TextField(blank=True, default='')
    attachment = models.FileField(
        upload_to='support_attachments/',
        null=True,
        blank=True,
        help_text='Optional image or document attached to reply.'
    )
    is_staff_reply = models.BooleanField(
        default=False,
        help_text='True if the reply was sent by a support agent / admin.'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Ticket Reply'
        verbose_name_plural = 'Ticket Replies'

    def __str__(self):
        role_label = "Staff" if self.is_staff_reply else "Customer"
        return f"Reply by {self.sender.username} ({role_label}) on Ticket #{self.ticket_id}"

    @property
    def is_image(self):
        if not self.attachment:
            return False
        ext = self.attachment.name.lower().split('.')[-1]
        return ext in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp']

    @property
    def is_pdf(self):
        if not self.attachment:
            return False
        return self.attachment.name.lower().endswith('.pdf')

    @property
    def filename(self):
        if self.attachment:
            import os
            return os.path.basename(self.attachment.name)
        return ""

    @property
    def file_size_display(self):
        if self.attachment and hasattr(self.attachment, 'size'):
            try:
                size = self.attachment.size
                if size < 1024:
                    return f"{size} B"
                elif size < 1024 * 1024:
                    return f"{size / 1024:.1f} KB"
                else:
                    return f"{size / (1024 * 1024):.1f} MB"
            except Exception:
                pass
        return ""

    @property
    def file_icon(self):
        if not self.attachment:
            return "fa-file"
        ext = self.attachment.name.lower().split('.')[-1]
        if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp']:
            return "fa-file-image text-success"
        elif ext == 'pdf':
            return "fa-file-pdf text-danger"
        elif ext in ['doc', 'docx']:
            return "fa-file-word text-primary"
        elif ext in ['xls', 'xlsx', 'csv']:
            return "fa-file-excel text-success"
        elif ext in ['zip', 'rar', 'tar', 'gz']:
            return "fa-file-zipper text-warning"
        return "fa-file-lines text-secondary"
