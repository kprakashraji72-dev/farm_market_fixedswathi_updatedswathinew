import json
import logging
from datetime import timedelta
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.conf import settings
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import support_staff_required
from .forms import CreateSupportStaffForm, SupportStaffLoginForm, SupportTicketForm
from .models import SupportTicket, TicketReply

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from django.http import JsonResponse
from django.views.decorators.http import require_POST

User = get_user_model()
logger = logging.getLogger(__name__)


def serialize_reply_data(reply, ticket=None):
    """Formats TicketReply into JSON-serializable dictionary with attachment info"""
    if not ticket:
        ticket = reply.ticket
    return {
        'id': reply.id,
        'message': reply.message,
        'is_staff_reply': reply.is_staff_reply,
        'sender_id': reply.sender_id,
        'sender_username': reply.sender.username,
        'sender_display': reply.sender.get_full_name() or reply.sender.username,
        'created_at_iso': reply.created_at.isoformat(),
        'created_at_formatted': reply.created_at.strftime("%b %d, %I:%M %p"),
        'ticket_status': ticket.status,
        'ticket_status_display': ticket.get_status_display(),
        'attachment_url': reply.attachment.url if reply.attachment else None,
        'attachment_name': reply.filename if reply.attachment else None,
        'is_image': reply.is_image if reply.attachment else False,
        'is_pdf': reply.is_pdf if reply.attachment else False,
        'file_size': reply.file_size_display if reply.attachment else None,
        'file_icon': reply.file_icon if reply.attachment else None,
    }


def broadcast_ticket_message(ticket_id, reply_data):
    """Safely broadcasts a newly created reply to WebSocket groups"""
    try:
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"ticket_{ticket_id}",
                {
                    'type': 'ticket_message',
                    'reply': reply_data,
                }
            )
            async_to_sync(channel_layer.group_send)(
                'support_console',
                {
                    'type': 'console_notification',
                    'event': 'new_reply',
                    'ticket_id': ticket_id,
                    'sender': reply_data.get('sender_username'),
                    'is_staff': reply_data.get('is_staff_reply'),
                    'message_preview': (reply_data.get('message') or ('[Attachment: ' + str(reply_data.get('attachment_name')) + ']'))[:80],
                }
            )
    except Exception as e:
        logger.warning(f"Could not broadcast ticket message: {e}")


def broadcast_ticket_status(ticket_id, status, status_display, resolved_at=None):
    """Safely broadcasts ticket status change to WebSocket groups"""
    try:
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"ticket_{ticket_id}",
                {
                    'type': 'ticket_status_changed',
                    'status': status,
                    'status_display': status_display,
                    'resolved_at': resolved_at,
                }
            )
            async_to_sync(channel_layer.group_send)(
                'support_console',
                {
                    'type': 'console_notification',
                    'event': 'status_change',
                    'ticket_id': ticket_id,
                    'new_status': status,
                    'new_status_display': status_display,
                }
            )
    except Exception as e:
        logger.warning(f"Could not broadcast ticket status: {e}")


def broadcast_new_ticket(ticket):
    """Safely broadcasts new ticket event to Support Console operators"""
    try:
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                'support_console',
                {
                    'type': 'ticket_created',
                    'ticket': {
                        'id': ticket.id,
                        'subject': ticket.subject,
                        'category': ticket.get_category_display(),
                        'customer': ticket.user.get_full_name() or ticket.user.username,
                        'customer_username': ticket.user.username,
                        'created_at_formatted': ticket.created_at.strftime("%b %d, %I:%M %p"),
                        'status': ticket.status,
                        'status_display': ticket.get_status_display(),
                    }
                }
            )
    except Exception as e:
        logger.warning(f"Could not broadcast new ticket: {e}")


# ==========================================
# AUTHENTICATION & STAFF MANAGEMENT
# ==========================================

def support_staff_login(request):
    """
    Dedicated login view for Support Staff.
    Only allows users with role == 'support_staff', 'admin', or is_superuser.
    """
    if request.user.is_authenticated:
        if request.user.is_superuser or request.user.role in [User.Role.SUPPORT_STAFF, User.Role.ADMIN]:
            next_url = request.GET.get('next') or request.POST.get('next')
            return redirect(next_url or 'customer_support:console')
        else:
            messages.error(request, "This account does not have Support Console access.")
            return redirect(request.user.get_dashboard_url_name())

    next_url = request.GET.get('next', '')

    if request.method == 'POST':
        form = SupportStaffLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()

            if not (user.is_superuser or user.role in [User.Role.SUPPORT_STAFF, User.Role.ADMIN]):
                messages.error(request, "This account does not have Support Console access.")
                return redirect('customer_support:login')

            if not user.is_active:
                messages.error(request, "This support staff account has been deactivated. Please contact an administrator.")
                return redirect('customer_support:login')

            login(request, user)
            messages.success(request, f"Welcome to the Support Console, {user.first_name or user.username}!")
            target_url = request.POST.get('next') or 'customer_support:console'
            return redirect(target_url)
        else:
            messages.error(request, "Invalid support staff username or password.")
    else:
        form = SupportStaffLoginForm()

    return render(request, 'customer_support/support_login.html', {
        'form': form,
        'next': next_url,
    })


def support_staff_logout(request):
    """Logs out staff and redirects back to the dedicated support login page."""
    logout(request)
    messages.info(request, "You have been logged out of the Support Console.")
    return redirect('customer_support:login')


@login_required
def manage_staff(request):
    """
    Superuser-only console to view and onboard support agents.
    """
    if not request.user.is_superuser:
        raise PermissionDenied("Only administrators can manage support staff accounts.")

    if request.method == 'POST':
        form = CreateSupportStaffForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            email = form.cleaned_data['email']
            first_name = form.cleaned_data['first_name']
            last_name = form.cleaned_data['last_name']
            password = form.cleaned_data['password']

            new_staff = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                role=User.Role.SUPPORT_STAFF,
                is_active=True,
                is_verified=True,
            )

            # Send onboarding email notification (without sending raw password)
            try:
                login_url = request.build_absolute_uri('/support-console/login/')
                send_mail(
                    subject="[Fresh Trace] Your Support Staff Account Has Been Created",
                    message=(
                        f"Hello {new_staff.first_name or new_staff.username},\n\n"
                        f"A Fresh Trace Support Staff account has been created for you.\n\n"
                        f"Username: {new_staff.username}\n"
                        f"Login URL: {login_url}\n\n"
                        f"Please sign in with the password provided by your administrator.\n\n"
                        f"Best regards,\nFresh Trace Administration"
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[new_staff.email],
                    fail_silently=True,
                )
            except Exception as e:
                logger.warning(f"Could not send support staff welcome email: {e}")

            messages.success(request, f"Support staff account '@{new_staff.username}' created successfully!")
            return redirect('customer_support:manage_staff')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = CreateSupportStaffForm()

    staff_members = (
        User.objects.filter(role=User.Role.SUPPORT_STAFF)
        .annotate(assigned_tickets_count=Count('assigned_support_tickets'))
        .order_by('-date_joined')
    )

    return render(request, 'customer_support/manage_staff.html', {
        'form': form,
        'staff_members': staff_members,
    })


@login_required
def toggle_staff_status(request, user_id):
    """
    Superuser-only action to activate or deactivate a support staff account safely (no hard deletion).
    """
    if not request.user.is_superuser:
        raise PermissionDenied("Only administrators can toggle staff account status.")

    staff_user = get_object_or_404(User, id=user_id, role=User.Role.SUPPORT_STAFF)
    
    if request.method == 'POST':
        staff_user.is_active = not staff_user.is_active
        staff_user.save(update_fields=['is_active'])
        status_label = "activated" if staff_user.is_active else "deactivated"
        messages.success(request, f"Account '@{staff_user.username}' has been {status_label}.")

    return redirect('customer_support:manage_staff')


# ==========================================
# SUPPORT CONSOLE STAFF VIEWS
# ==========================================

@support_staff_required
def support_console(request):
    """
    Main Support Staff Console mirroring the Driver Dispatch Console layout.
    Displays 4 metric cards, search/filter toolbar, and 2-column ticket card grid.
    """
    tickets_qs = (
        SupportTicket.objects.select_related(
            'user', 'assigned_to', 'order', 'order__driver', 'order__customer'
        )
        .prefetch_related('order__items', 'replies')
        .order_by('-created_at')
    )

    # Metrics
    total_tickets = tickets_qs.count()
    open_tickets = tickets_qs.filter(status='open').count()
    in_progress_tickets = tickets_qs.filter(status='in_progress').count()
    
    today = timezone.now().date()
    resolved_today = tickets_qs.filter(
        status__in=['resolved', 'closed'],
        resolved_at__date=today
    ).count()

    # Filter Controls
    status_filter = request.GET.get('status', '')
    category_filter = request.GET.get('category', '')
    assigned_filter = request.GET.get('assigned', '')
    search_query = request.GET.get('q', '').strip()

    if status_filter:
        tickets_qs = tickets_qs.filter(status=status_filter)
    if category_filter:
        tickets_qs = tickets_qs.filter(category=category_filter)
    if assigned_filter:
        if assigned_filter == 'unassigned':
            tickets_qs = tickets_qs.filter(assigned_to__isnull=True)
        elif assigned_filter == 'me':
            tickets_qs = tickets_qs.filter(assigned_to=request.user)
        else:
            tickets_qs = tickets_qs.filter(assigned_to_id=assigned_filter)
    if search_query:
        tickets_qs = tickets_qs.filter(
            Q(subject__icontains=search_query) |
            Q(message__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(order__id__icontains=search_query)
        )

    staff_members = User.objects.filter(
        Q(is_superuser=True) | Q(role__in=['support_staff', 'admin']),
        is_active=True
    ).distinct().order_by('username')

    return render(request, 'customer_support/console.html', {
        'tickets': tickets_qs,
        'total_tickets': total_tickets,
        'open_tickets': open_tickets,
        'in_progress_tickets': in_progress_tickets,
        'resolved_today': resolved_today,
        'staff_members': staff_members,
        'current_status': status_filter,
        'current_category': category_filter,
        'current_assigned': assigned_filter,
        'search_query': search_query,
    })


@support_staff_required
def ticket_detail(request, pk):
    """
    Detailed Support Console view with full conversation thread,
    order/product/delivery context, reply composer, and status changer.
    """
    ticket = get_object_or_404(
        SupportTicket.objects.select_related(
            'user', 'assigned_to', 'order', 'order__driver', 'order__customer'
        ).prefetch_related('order__items', 'replies', 'replies__sender'),
        pk=pk
    )

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'reply_and_update':
            reply_message = request.POST.get('message', '').strip()
            attachment_file = request.FILES.get('attachment')
            new_status = request.POST.get('status', ticket.status)
            assigned_to_id = request.POST.get('assigned_to', '')

            # Create staff reply
            if reply_message or attachment_file:
                reply = TicketReply.objects.create(
                    ticket=ticket,
                    sender=request.user,
                    message=reply_message,
                    attachment=attachment_file,
                    is_staff_reply=True
                )

                # Broadcast reply via WebSocket
                broadcast_ticket_message(ticket.id, serialize_reply_data(reply, ticket))

                # Send email notification to customer
                try:
                    if ticket.user.email:
                        msg_preview = reply_message or (f"[Attached File: {reply.filename}]")
                        send_mail(
                            subject=f"[Fresh Trace Support] Reply on Ticket #{ticket.id}: {ticket.subject}",
                            message=(
                                f"Hello {ticket.user.first_name or ticket.user.username},\n\n"
                                f"Our support team has posted a reply to your ticket #{ticket.id}:\n\n"
                                f"--------------------------------------------------\n"
                                f"{msg_preview}\n"
                                f"--------------------------------------------------\n\n"
                                f"Status: {ticket.get_status_display()}\n\n"
                                f"You can view the full thread and reply at:\n"
                                f"{request.build_absolute_uri('/support/tickets/' + str(ticket.id) + '/')}\n\n"
                                f"Best regards,\nFresh Trace Support Team"
                            ),
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            recipient_list=[ticket.user.email],
                            fail_silently=True,
                        )
                except Exception as e:
                    logger.warning(f"Failed to email customer regarding staff ticket reply: {e}")

            # Status update
            old_status = ticket.status
            if new_status in dict(SupportTicket.Status.choices):
                ticket.status = new_status
                if new_status in ['resolved', 'closed']:
                    if not ticket.resolved_at:
                        ticket.resolved_at = timezone.now()
                else:
                    ticket.resolved_at = None

            # Agent assignment
            if assigned_to_id:
                try:
                    ticket.assigned_to = User.objects.get(pk=assigned_to_id)
                except User.DoesNotExist:
                    pass
            elif assigned_to_id == '':
                ticket.assigned_to = None

            ticket.save()

            if old_status != ticket.status:
                broadcast_ticket_status(
                    ticket.id,
                    ticket.status,
                    ticket.get_status_display(),
                    ticket.resolved_at.isoformat() if ticket.resolved_at else None
                )

            messages.success(request, f"Ticket #{ticket.id} updated successfully.")
            return redirect('customer_support:detail', pk=ticket.pk)

    replies = ticket.replies.select_related('sender').order_by('created_at')
    
    staff_members = User.objects.filter(
        Q(is_superuser=True) | Q(role__in=['support_staff', 'admin']),
        is_active=True
    ).distinct().order_by('username')

    return render(request, 'customer_support/ticket_detail.html', {
        'ticket': ticket,
        'replies': replies,
        'staff_members': staff_members,
    })


@support_staff_required
def reassign_ticket(request, pk):
    """
    Quick POST endpoint to reassign a ticket directly from the console card.
    """
    if request.method == 'POST':
        ticket = get_object_or_404(SupportTicket, pk=pk)
        assigned_to_id = request.POST.get('assigned_to', '')
        
        if assigned_to_id:
            try:
                ticket.assigned_to = User.objects.get(pk=assigned_to_id)
                messages.success(request, f"Ticket #{ticket.id} reassigned to {ticket.assigned_to.username}.")
            except User.DoesNotExist:
                messages.error(request, "Staff member not found.")
        else:
            ticket.assigned_to = None
            messages.info(request, f"Ticket #{ticket.id} is now unassigned.")
            
        ticket.save(update_fields=['assigned_to', 'updated_at'])
    return redirect('customer_support:console')


@support_staff_required
def reports(request):
    """
    Analytics & Reporting dashboard for Support Console.
    """
    tickets = SupportTicket.objects.all()

    category_counts = {}
    for code, label in SupportTicket.Category.choices:
        category_counts[label] = tickets.filter(category=code).count()

    status_counts = {
        'Open': tickets.filter(status='open').count(),
        'In Progress': tickets.filter(status='in_progress').count(),
        'Resolved': tickets.filter(status='resolved').count(),
        'Closed': tickets.filter(status='closed').count(),
    }

    today = timezone.now().date()
    days_labels = []
    days_data = []
    for i in range(29, -1, -1):
        day = today - timedelta(days=i)
        days_labels.append(day.strftime('%b %d'))
        count = tickets.filter(created_at__date=day).count()
        days_data.append(count)

    resolved_tickets = tickets.filter(resolved_at__isnull=False)
    total_res_secs = 0
    res_count = 0
    for t in resolved_tickets:
        if t.resolved_at and t.created_at:
            delta = (t.resolved_at - t.created_at).total_seconds()
            if delta > 0:
                total_res_secs += delta
                res_count += 1
    avg_resolution_hours = round(total_res_secs / (res_count * 3600), 1) if res_count > 0 else 0

    top_customers = (
        User.objects.filter(support_tickets__isnull=False)
        .annotate(ticket_count=Count('support_tickets'))
        .order_by('-ticket_count')[:10]
    )

    return render(request, 'customer_support/reports.html', {
        'total_tickets': tickets.count(),
        'category_counts': category_counts,
        'status_counts': status_counts,
        'category_labels_json': json.dumps(list(category_counts.keys())),
        'category_values_json': json.dumps(list(category_counts.values())),
        'status_labels_json': json.dumps(list(status_counts.keys())),
        'status_values_json': json.dumps(list(status_counts.values())),
        'trend_labels_json': json.dumps(days_labels),
        'trend_values_json': json.dumps(days_data),
        'avg_resolution_hours': avg_resolution_hours,
        'resolved_count': res_count,
        'top_customers': top_customers,
    })


# ==========================================
# CUSTOMER FACING SUPPORT VIEWS
# ==========================================

@login_required
def customer_create(request):
    """Customer-facing contact form with FAQ accordion."""
    if request.method == 'POST':
        form = SupportTicketForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.user = request.user
            ticket.save()

            # Broadcast new ticket to support console via WebSocket
            broadcast_new_ticket(ticket)

            try:
                if request.user.email:
                    send_mail(
                        subject=f"[Fresh Trace] Support Ticket #{ticket.id} Received: {ticket.subject}",
                        message=(
                            f"Hello {request.user.first_name or request.user.username},\n\n"
                            f"Thank you for contacting Fresh Trace Support. We have received your inquiry:\n\n"
                            f"Ticket ID: #{ticket.id}\n"
                            f"Subject: {ticket.subject}\n"
                            f"Category: {ticket.get_category_display()}\n\n"
                            f"Our support team will review your inquiry shortly.\n\n"
                            f"Best regards,\nFresh Trace Support Team"
                        ),
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[request.user.email],
                        fail_silently=True,
                    )
            except Exception as e:
                logger.warning(f"Could not send support ticket confirmation email: {e}")

            messages.success(
                request,
                f"Support Ticket #{ticket.id} submitted successfully! We will get back to you shortly."
            )
            return redirect('support:my_tickets')
        else:
            messages.error(request, "Please correct the errors in the support form below.")
    else:
        order_id = request.GET.get('order_id')
        initial_data = {}
        if order_id:
            initial_data['order'] = order_id
        form = SupportTicketForm(user=request.user, initial=initial_data)

    return render(request, 'support/support_form.html', {
        'form': form,
    })


@login_required
def customer_my_tickets(request):
    """Customer-facing list of their own tickets."""
    tickets = SupportTicket.objects.filter(user=request.user).order_by('-created_at')
    
    total_count = tickets.count()
    open_count = tickets.filter(status__in=['open', 'in_progress']).count()
    resolved_count = tickets.filter(status__in=['resolved', 'closed']).count()

    return render(request, 'support/my_tickets.html', {
        'tickets': tickets,
        'total_count': total_count,
        'open_count': open_count,
        'resolved_count': resolved_count,
    })


@login_required
def customer_ticket_detail(request, pk):
    """Customer-facing ticket detail with conversation thread & reply composer."""
    ticket = get_object_or_404(SupportTicket, pk=pk)
    
    if ticket.user != request.user and not (request.user.is_superuser or request.user.role in ['support_staff', 'admin']):
        raise PermissionDenied("You do not have permission to view this support ticket.")

    if request.method == 'POST':
        message_text = request.POST.get('message', '').strip()
        attachment_file = request.FILES.get('attachment')
        if message_text or attachment_file:
            reply = TicketReply.objects.create(
                ticket=ticket,
                sender=request.user,
                message=message_text,
                attachment=attachment_file,
                is_staff_reply=False
            )
            old_status = ticket.status
            if ticket.status in ['resolved', 'closed']:
                ticket.status = 'in_progress'
                ticket.resolved_at = None
                ticket.save(update_fields=['status', 'resolved_at', 'updated_at'])
            else:
                ticket.updated_at = timezone.now()
                ticket.save(update_fields=['updated_at'])

            # Broadcast reply via WebSocket
            broadcast_ticket_message(ticket.id, serialize_reply_data(reply, ticket))

            if old_status != ticket.status:
                broadcast_ticket_status(
                    ticket.id,
                    ticket.status,
                    ticket.get_status_display(),
                    None
                )

            messages.success(request, "Your reply has been posted.")
            return redirect('support:detail', pk=ticket.pk)
        else:
            messages.error(request, "Please enter a message or select a file before replying.")

    replies = ticket.replies.select_related('sender').order_by('created_at')

    return render(request, 'support/ticket_detail.html', {
        'ticket': ticket,
        'replies': replies,
    })


@login_required
@require_POST
def upload_ticket_attachment(request, pk):
    """
    Async AJAX endpoint for WhatsApp chat media & document uploads.
    Accepts multipart/form-data containing 'attachment' and optional 'message'.
    Broadcasts message instantly over WebSocket to all active room subscribers.
    """
    ticket = get_object_or_404(SupportTicket, pk=pk)
    is_staff = request.user.is_superuser or getattr(request.user, 'role', '') in ['support_staff', 'admin']
    
    # Permission verification
    if not is_staff and ticket.user_id != request.user.id:
        return JsonResponse({'status': 'error', 'message': 'Permission denied.'}, status=403)

    message_text = request.POST.get('message', '').strip()
    attachment_file = request.FILES.get('attachment')

    if not message_text and not attachment_file:
        return JsonResponse({'status': 'error', 'message': 'Message or attachment is required.'}, status=400)

    reply = TicketReply.objects.create(
        ticket=ticket,
        sender=request.user,
        message=message_text,
        attachment=attachment_file,
        is_staff_reply=is_staff
    )

    old_status = ticket.status
    if not is_staff and ticket.status in ['resolved', 'closed']:
        ticket.status = 'in_progress'
        ticket.resolved_at = None
        ticket.save(update_fields=['status', 'resolved_at', 'updated_at'])
    else:
        ticket.updated_at = timezone.now()
        ticket.save(update_fields=['updated_at'])

    reply_data = serialize_reply_data(reply, ticket)
    broadcast_ticket_message(ticket.id, reply_data)

    if old_status != ticket.status:
        broadcast_ticket_status(
            ticket.id,
            ticket.status,
            ticket.get_status_display(),
            ticket.resolved_at.isoformat() if ticket.resolved_at else None
        )

    return JsonResponse({'status': 'ok', 'reply': reply_data})

