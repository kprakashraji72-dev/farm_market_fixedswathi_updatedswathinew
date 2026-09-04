"""
Email notifications for the driver/farmer partner verification flow.
Kept as plain functions (not signals) so the trigger is explicit and
visible at the call site in dashboard.views.driver_toggle_verified —
easier to trace than a signal that fires on any User.save().
"""
import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def send_partner_verification_email(user, verified: bool):
    """
    Notifies a driver or farmer that an admin just verified (or
    un-verified) their account. Never raises — a broken/unconfigured
    mail server shouldn't block the admin's verification action, so
    failures are logged instead of surfaced to the admin as an error.
    """
    if not user.email:
        return

    role_label = 'delivery partner' if user.role == 'driver' else 'farm partner'
    login_path = '/accounts/driver/login/' if user.role == 'driver' else '/accounts/farmer/login/'

    if verified:
        subject = 'Your Fresh Trace application has been verified ✅'
        message = (
            f"Hi {user.first_name or user.username},\n\n"
            f"Good news — your {role_label} account on Fresh Trace has been verified by our team. "
            f"You can now log in and get started:\n\n"
            f"{login_path}\n\n"
            f"— Fresh Trace"
        )
    else:
        subject = 'Your Fresh Trace verification was reset'
        message = (
            f"Hi {user.first_name or user.username},\n\n"
            f"Your {role_label} account on Fresh Trace has been marked as unverified. "
            f"This usually means a document needs another look — please check your submitted "
            f"documents and reach out if you have questions.\n\n"
            f"— Fresh Trace"
        )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception:
        logger.exception('Failed to send verification email to %s', user.email)


def send_password_reset_email(user, new_password):
    """
    Emails a driver/farmer/employee/customer the new temporary password an
    admin just set for them (dashboard.views.user_reset_password). Same
    best-effort pattern as the other notifications here — a broken/
    unconfigured mail server never blocks the admin's action, it's just
    logged, since the admin also sees the password on-screen to relay
    manually if email delivery fails.
    """
    if not user.email:
        return
    try:
        send_mail(
            subject='Your Fresh Trace password was reset',
            message=(
                f"Hi {user.first_name or user.username},\n\n"
                f"An admin reset the password on your Fresh Trace account.\n\n"
                f"Your new temporary password is:\n\n"
                f"    {new_password}\n\n"
                f"Please log in and change it from your profile as soon as possible.\n\n"
                f"— Fresh Trace"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception:
        logger.exception('Failed to send password reset email to %s', user.email)


def send_partner_application_received_email(user):
    """Confirms receipt right after a driver/farmer submits their signup + KYC docs."""
    if not user.email:
        return
    role_label = 'delivery partner' if user.role == 'driver' else 'farm partner'
    try:
        send_mail(
            subject='We received your Fresh Trace application',
            message=(
                f"Hi {user.first_name or user.username},\n\n"
                f"Thanks for applying to become a Fresh Trace {role_label}! We've received your "
                f"account details and documents. An admin will review them shortly, and you'll "
                f"get another email as soon as you're verified and able to log in.\n\n"
                f"— Fresh Trace"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception:
        logger.exception('Failed to send application-received email to %s', user.email)
