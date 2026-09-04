"""
Guest order tracking, by order number + mobile number — no login required.

Flow:
  1. Customer visits the public lookup page and enters their order number
     and the mobile number used at checkout.
  2. track_lookup_view (in views.py) verifies they match, then remembers
     that order id in the session (SESSION_KEY below) — this session is
     the "ticket" that grants access to that one order's tracking page
     and its location-polling API, without needing an account.
  3. can_track_order() is the single check both orders.order_detail_view
     and tracking.order_location_api use to decide whether the current
     request (logged-in owner, admin, driver, or verified guest session)
     may view a given order.
"""
import re

SESSION_KEY = 'tracked_order_ids'


def normalize_phone(raw):
    """
    Digits only, last 10 kept, so '+91 98765-43210', '919876543210', and
    '9876543210' all compare equal regardless of country-code prefix or
    formatting.
    """
    digits = re.sub(r'\D', '', raw or '')
    return digits[-10:] if len(digits) >= 10 else digits


def grant_guest_access(request, order):
    """Remember in the session that this browser verified order+phone."""
    tracked = set(request.session.get(SESSION_KEY, []))
    tracked.add(order.id)
    request.session[SESSION_KEY] = list(tracked)


def has_guest_access(request, order_id):
    return order_id in request.session.get(SESSION_KEY, [])


def can_track_order(request, order):
    """
    True if the current request is allowed to view/poll this order:
      - the order's own customer (logged in)
      - an admin
      - the driver it's assigned to
      - a guest who verified via order number + phone on the lookup page
    """
    user = request.user
    if user.is_authenticated:
        if user.id == order.customer_id or user.role == 'admin':
            return True
        if order.driver_id and user.id == order.driver_id:
            return True
    return has_guest_access(request, order.id)
