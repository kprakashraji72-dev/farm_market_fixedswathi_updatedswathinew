"""
Driver assignment logic, shared by:
  - checkout_view (auto-assign right when the order is placed)
  - dashboard.order_auto_assign_driver (the admin's "Auto-assign" button)

Selection strategy — First-In-First-Out (FIFO) dispatch queue:
  1. Only verified drivers (role='driver', is_verified=True) are eligible.
  2. Prefer drivers currently marked online (tracking.DriverLocation.is_online).
  3. Among those, pick whoever has gone the LONGEST without receiving an
     order — i.e. sorted by last_order_assigned_at ascending, with drivers
     who have never been assigned an order (NULL) going first of all.
     This is the "first login, first out" queue: whoever has been
     available longest gets the next order, then goes to the back of the
     line. It keeps dispatch fair instead of always picking the same
     driver every time.
  4. If no online drivers exist, fall back to the same FIFO ordering
     across ALL verified drivers (even offline), so an order still gets
     assigned to someone rather than sitting unassigned.
  5. If no verified driver exists at all, return None — the order is left
     for an admin to assign manually from the dashboard.
"""
from django.contrib.auth import get_user_model
from django.db.models import F

User = get_user_model()


def find_best_driver(order):
    """Return the next driver in the FIFO dispatch queue for `order`, or None."""
    verified_drivers = User.objects.filter(
        role=User.Role.DRIVER, is_verified=True
    ).select_related('location')
    if not verified_drivers.exists():
        verified_drivers = User.objects.filter(
            role=User.Role.DRIVER
        ).select_related('location')
        if not verified_drivers.exists():
            return None

    online_drivers = [d for d in verified_drivers if getattr(d, 'location', None) and d.location.is_online]
    candidates = online_drivers or list(verified_drivers)

    # FIFO: never-assigned (None) drivers first, then oldest last_order_assigned_at first.
    candidates.sort(key=lambda d: (d.last_order_assigned_at is not None, d.last_order_assigned_at))
    return candidates[0]


def assign_driver(order, driver):
    """
    Assign `driver` to `order`, bump PENDING -> CONFIRMED, and send them to
    the back of the FIFO dispatch queue (last_order_assigned_at = now) so
    the next order goes to whoever's been waiting longest.

    Note: the delivery OTP is NOT generated here anymore — it's only
    generated once the driver confirms they've physically arrived at the
    customer's location (see tracking.views.driver_confirm_arrival).
    """
    from django.utils import timezone

    order.driver = driver
    if order.status == order.Status.PENDING:
        order.status = order.Status.CONFIRMED
    order.save(update_fields=['driver', 'status'])

    driver.last_order_assigned_at = timezone.now()
    driver.save(update_fields=['last_order_assigned_at'])




def cancel_order(order):
    """
    Cancel `order` and give the stock back — shared by the customer's
    self-service Cancel button and the admin's manual status change, so
    stock restoration only ever happens in one place.

    Returns True if the order was cancelled, False if it was already
    cancelled or already past the point where the customer/admin should
    be cancelling it here (out for delivery or delivered).
    """
    from inventory.models import Product, ProductVariant
    from .models import Order

    if order.status in (Order.Status.CANCELLED, Order.Status.OUT_FOR_DELIVERY, Order.Status.DELIVERED):
        return False

    for item in order.items.all():
        if item.variant_id:
            ProductVariant.objects.filter(pk=item.variant_id).update(
                stock_quantity=F('stock_quantity') + item.quantity
            )
        elif item.product_id:
            Product.objects.filter(pk=item.product_id).update(
                stock_quantity=F('stock_quantity') + item.quantity
            )

    order.status = Order.Status.CANCELLED
    order.save(update_fields=['status'])
    return True


def unassign_driver(order, reason=''):
    """
    Driver-initiated reject/unassign. Only valid while the order hasn't
    been picked up yet (CONFIRMED, not OUT_FOR_DELIVERY) — once a driver
    has physically picked up the order they can't just drop it, that
    needs an admin/support path instead.

    Clears the driver, resets status back to PENDING so try_auto_assign
    can pick it up for the next available driver, and stamps
    last_order_assigned_at forward on the rejecting driver so FIFO
    dispatch doesn't immediately hand it right back to them.
    """
    from django.utils import timezone
    from .models import Order

    if order.status != Order.Status.CONFIRMED or not order.driver_id:
        return False

    order.driver.last_order_assigned_at = timezone.now()
    order.driver.save(update_fields=['last_order_assigned_at'])

    order.driver = None
    order.status = Order.Status.PENDING
    order.save(update_fields=['driver', 'status'])

    try_auto_assign(order)
    return True


def try_auto_assign(order):
    """
    Attempt to auto-assign a driver to `order` if it doesn't already have one.
    Returns True if a driver ended up assigned (already-assigned counts as
    success), False if no driver was available — the order simply stays
    PENDING/unassigned until an admin assigns one manually.
    """
    if order.driver_id:
        return True

    driver = find_best_driver(order)
    if driver is None:
        return False

    assign_driver(order, driver)
    return True
