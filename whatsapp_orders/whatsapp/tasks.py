"""
whatsapp/tasks.py
─────────────────
Celery asynchronous tasks for WhatsApp Flow ordering:
1. send_confirmation_task(order_id): Formats & dispatches WhatsApp order confirmation.
2. cleanup_stale_sessions_task(): Deletes or marks stale FlowSessions older than 24h (status != complete).
"""

import logging
from datetime import timedelta
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def send_confirmation_task(self, order_id: int):
    """
    Asynchronously sends WhatsApp order confirmation to the customer.
    """
    from orders.models import Order
    from .services import send_order_confirmation

    try:
        order = Order.objects.select_related("product", "session").get(pk=order_id)
        res = send_order_confirmation(order)
        logger.info("[Celery] send_confirmation_task for Order #%s result: %s", order_id, res)
        return res
    except Order.DoesNotExist:
        logger.error("[Celery] Order #%s not found for confirmation task.", order_id)
        return {"success": False, "error": "Order not found"}
    except Exception as exc:
        logger.exception("[Celery] Error in send_confirmation_task for Order #%s: %s", order_id, exc)
        raise self.retry(exc=exc)


@shared_task
def cleanup_stale_sessions_task():
    """
    Cleans up incomplete FlowSession records older than 24 hours.
    """
    from orders.models import FlowSession

    threshold = timezone.now() - timedelta(hours=24)
    stale_qs = FlowSession.objects.filter(
        created_at__lt=threshold
    ).exclude(
        status=FlowSession.Status.COMPLETE
    )
    count = stale_qs.count()
    stale_qs.delete()
    logger.info("[Celery] Cleaned up %d stale FlowSession records.", count)
    return {"cleaned_sessions": count}
