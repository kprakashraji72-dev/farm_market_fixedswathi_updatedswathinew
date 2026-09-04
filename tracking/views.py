"""
Tracking views:
  - driver_dashboard     : driver's own page — lists assigned deliveries.
  - driver_delivery_page : dedicated live delivery page with turn-by-turn map,
                           route display, GPS broadcasting & action buttons.
  - update_location      : AJAX POST target — receives live lat/lng from
                           driver's browser, updates DriverLocation, logs
                           breadcrumb in DeliveryLocationLog, and auto-detects arrival.
  - order_location_api   : AJAX GET target polled by Customer Track Order page
                           and Rider Delivery page — returns live rider, customer,
                           and farm pickup coordinates, blue route info, distance,
                           and dynamic ETA.
"""
import json
from math import radians, sin, cos, sqrt, atan2
from datetime import timedelta

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET

from accounts.decorators import driver_required
from orders.access import can_track_order
from orders.models import Order
from orders.services import unassign_driver
from .models import DriverLocation, DeliveryLocationLog

# How close (in metres) the driver's live GPS must be to the customer's
# delivery coordinates before "I've Arrived" is accepted and the OTP
# is generated. Loose enough to allow for phone GPS drift/parking spots.
ARRIVAL_RADIUS_METRES = 300


def _distance_metres(lat1, lon1, lat2, lon2):
    """Haversine distance between two coordinates in metres."""
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return 0.0
    try:
        lat1, lon1, lat2, lon2 = (radians(float(v)) for v in (lat1, lon1, lat2, lon2))
    except (ValueError, TypeError):
        return 0.0
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371000 * 2 * atan2(sqrt(a), sqrt(1 - a))


def _calculate_eta(distance_metres, average_speed_kmh=25.0):
    """
    Calculates estimated travel time given distance in metres and average speed in km/h.
    Returns (minutes_int, formatted_eta_str, arrival_timestamp_iso).
    """
    if distance_metres <= 0:
        return 0, "Arrived", timezone.now().isoformat()
    # Speed in m/s
    speed_mps = (average_speed_kmh * 1000) / 3600
    seconds = distance_metres / speed_mps
    # Add 2 minutes for traffic/signals
    minutes = max(1, int(round((seconds / 60) + 2)))
    eta_time = timezone.now() + timedelta(minutes=minutes)
    local_eta = timezone.localtime(eta_time)
    formatted_eta = f"{minutes} min{'s' if minutes != 1 else ''} ({local_eta.strftime('%I:%M %p').lstrip('0')})"
    return minutes, formatted_eta, eta_time.isoformat()


def _auto_detect_arrivals(driver, lat, lng):
    """
    Called on every `update_location` ping. Looks at this driver's
    OUT_FOR_DELIVERY orders that haven't been marked arrived yet and
    that captured GPS at checkout, and generates the OTP the moment the
    driver's live position is within ARRIVAL_RADIUS_METRES — fully
    automatic, no manual "I've Arrived" tap.
    """
    candidates = Order.objects.filter(
        driver=driver,
        status=Order.Status.OUT_FOR_DELIVERY,
        arrived_at__isnull=True,
        delivery_latitude__isnull=False,
        delivery_longitude__isnull=False,
    )

    newly_arrived = []
    for order in candidates:
        distance = _distance_metres(order.delivery_latitude, order.delivery_longitude, lat, lng)
        if distance <= ARRIVAL_RADIUS_METRES:
            order.generate_otp()
            order.arrived_at = timezone.now()
            order.save(update_fields=['delivery_otp', 'arrived_at'])
            newly_arrived.append(order.id)
    return newly_arrived


@driver_required
def driver_dashboard(request):
    """
    Landing page after driver login. Lists orders assigned to this driver
    that are confirmed/out-for-delivery, and renders stats + quick actions.
    """
    from django.db.models import Sum

    assigned_orders = Order.objects.filter(
        driver=request.user,
        status__in=[Order.Status.CONFIRMED, Order.Status.OUT_FOR_DELIVERY],
    ).select_related('customer').prefetch_related('items__product__farm')

    delivered_orders = Order.objects.filter(driver=request.user, status=Order.Status.DELIVERED)

    today = timezone.localdate()
    today_delivered = delivered_orders.filter(otp_verified_at__date=today)

    stats = {
        'active_orders_count': assigned_orders.count(),
        'total_orders_count': Order.objects.filter(driver=request.user).exclude(status=Order.Status.CANCELLED).count(),
        'delivered_count': delivered_orders.count(),
        'total_earnings': delivered_orders.aggregate(total=Sum('delivery_fee'))['total'] or 0,
        'today_delivered_count': today_delivered.count(),
        'today_earnings': today_delivered.aggregate(total=Sum('delivery_fee'))['total'] or 0,
    }

    return render(request, 'store/driver_dashboard.html', {
        'assigned_orders': assigned_orders,
        'stats': stats,
    })


@driver_required
def driver_delivery_page(request, order_id):
    """
    Dedicated delivery workspace page for the rider.
    Displays:
      - Rider's live GPS location
      - Customer delivery location
      - Farm / store pickup location
      - Blue route to customer with live distance & ETA
      - Customer details & Order details
      - Action buttons: [ Accept Order ], [ Start Delivery ], [ Navigate ], [ Mark Delivered ]
      - Live GPS broadcasting controller
    """
    order = get_object_or_404(Order.objects.select_related('customer').prefetch_related('items__product__farm'), id=order_id, driver=request.user)

    # Driver's current location from DB if available
    driver_loc = getattr(request.user, 'location', None)

    # Calculate initial distance & ETA if coordinates exist
    dist_m = 0
    eta_str = "Calculating..."
    start_lat = driver_loc.latitude if driver_loc else order.pickup_latitude
    start_lng = driver_loc.longitude if driver_loc else order.pickup_longitude
    dest_lat = order.delivery_latitude or 13.050000
    dest_lng = order.delivery_longitude or 80.212000

    if start_lat and start_lng and dest_lat and dest_lng:
        dist_m = _distance_metres(start_lat, start_lng, dest_lat, dest_lng)
        _, eta_str, _ = _calculate_eta(dist_m, 25.0)

    dist_display = f"{dist_m / 1000:.1f} km" if dist_m >= 1000 else f"{int(dist_m)} m"

    return render(request, 'store/rider_delivery.html', {
        'order': order,
        'driver_loc': driver_loc,
        'dist_display': dist_display,
        'eta_display': eta_str,
    })


@require_POST
@driver_required
def driver_pick_order(request, order_id):
    """
    Driver accepts/picks up order moving CONFIRMED -> OUT_FOR_DELIVERY.
    """
    order = get_object_or_404(Order, id=order_id, driver=request.user)
    if order.status == Order.Status.CONFIRMED or order.status == Order.Status.PENDING:
        order.status = Order.Status.OUT_FOR_DELIVERY
        order.picked_up_at = timezone.now()
        order.save(update_fields=['status', 'picked_up_at'])
        
        # Send WhatsApp Out For Delivery notification (Template 2)
        try:
            from whatsapp_webhook.services import send_out_for_delivery_notification
            send_out_for_delivery_notification(order)
        except Exception as wa_err:
            import logging
            logging.getLogger(__name__).warning("Failed to dispatch WhatsApp Out For Delivery message for Order #%s: %s", order.id, wa_err)

        messages.success(request, f'Order #{order.id} started — live GPS location tracking is now active.')
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
        return JsonResponse({'success': True, 'status': order.status, 'status_display': order.get_status_display()})

    return redirect('tracking:driver_delivery_page', order_id=order.id)


@require_POST
@driver_required
def driver_start_delivery(request, order_id):
    """
    Action button handler for [ Start Delivery ].
    Transitions order to OUT_FOR_DELIVERY and stamps picked_up_at.
    """
    return driver_pick_order(request, order_id)


@require_POST
@driver_required
def driver_reject_order(request, order_id):
    """
    Driver declines an order assigned to them before pickup.
    """
    order = get_object_or_404(Order, id=order_id, driver=request.user)
    if unassign_driver(order):
        messages.success(request, f'Order #{order.id} has been released back to the queue.')
    else:
        messages.error(request, f'Order #{order.id} can no longer be released — it may already be picked up.')
    return redirect('tracking:driver_dashboard')


@require_POST
@driver_required
def driver_confirm_arrival(request, order_id):
    """
    Manual fallback for arrival confirmation when GPS is not available.
    """
    order = get_object_or_404(Order, id=order_id, driver=request.user)

    if order.status != Order.Status.OUT_FOR_DELIVERY:
        messages.error(request, 'Start the delivery before confirming arrival.')
        return redirect('tracking:driver_delivery_page', order_id=order.id)

    if order.arrived_at:
        messages.info(request, f'Already marked as arrived for Order #{order.id}.')
        return redirect('tracking:driver_delivery_page', order_id=order.id)

    order.generate_otp()
    order.arrived_at = timezone.now()
    order.save(update_fields=['delivery_otp', 'arrived_at'])
    messages.success(request, f'Arrival confirmed for Order #{order.id} — OTP generated.')

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
        return JsonResponse({'success': True, 'arrived': True})

    return redirect('tracking:driver_delivery_page', order_id=order.id)


@require_POST
@driver_required
def driver_complete_order(request, order_id):
    """
    Driver completes the delivery by verifying OTP or one-click verification.
    """
    order = get_object_or_404(Order, id=order_id, driver=request.user)
    entered_otp = (request.POST.get('otp') or '').strip()

    if order.status != Order.Status.OUT_FOR_DELIVERY:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Order is not in Out for Delivery status.'}, status=400)
        messages.error(request, 'Pick up and start delivery before completing order.')
        return redirect('tracking:driver_delivery_page', order_id=order.id)

    # If order has OTP generated, verify it (or allow direct completion if OTP matches or auto-verified)
    if order.delivery_otp and entered_otp and entered_otp != order.delivery_otp:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Incorrect OTP. Please ask the customer to confirm the code and try again.'}, status=400)
        messages.error(request, 'Incorrect OTP. Please ask the customer to confirm the code and try again.')
        return redirect('tracking:driver_delivery_page', order_id=order.id)

    order.status = Order.Status.DELIVERED
    order.otp_verified_at = timezone.now()
    if not order.arrived_at:
        order.arrived_at = timezone.now()
    order.save(update_fields=['status', 'otp_verified_at', 'arrived_at'])
    
    # Send WhatsApp delivery confirmation template (hello_world) to customer upon OTP verification
    try:
        from whatsapp_webhook.services import send_delivery_otp_matched_confirmation
        send_delivery_otp_matched_confirmation(order)
    except Exception as wa_err:
        import logging
        logging.getLogger(__name__).warning("Failed to dispatch WhatsApp delivery confirmation for Order #%s: %s", order.id, wa_err)

    messages.success(request, f'Order #{order.id} successfully marked as delivered! Great work.')

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'delivered': True, 'message': 'Delivery successfully completed!'})

    return redirect('tracking:driver_dashboard')


@require_POST
@driver_required
def update_location(request):
    """
    Receives {latitude, longitude, accuracy, speed, heading, order_id}
    from navigator.geolocation and upserts DriverLocation + logs breadcrumb.
    """
    try:
        data = json.loads(request.body)
        lat = float(data['latitude'])
        lng = float(data['longitude'])
        accuracy = data.get('accuracy')
        speed = data.get('speed')
        heading = data.get('heading')
        order_id = data.get('order_id')
    except (KeyError, ValueError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Invalid location payload.'}, status=400)

    # Upsert latest live location
    DriverLocation.objects.update_or_create(
        driver=request.user,
        defaults={
            'latitude': lat,
            'longitude': lng,
            'accuracy_metres': accuracy,
            'speed': speed,
            'heading': heading,
            'is_online': True,
        },
    )

    # Log route breadcrumb for active order if present
    active_order = None
    if order_id:
        active_order = Order.objects.filter(id=order_id, driver=request.user).first()
    if not active_order:
        active_order = Order.objects.filter(driver=request.user, status=Order.Status.OUT_FOR_DELIVERY).first()

    if active_order:
        DeliveryLocationLog.objects.create(
            order=active_order,
            driver=request.user,
            latitude=lat,
            longitude=lng,
            accuracy_metres=accuracy,
            speed=speed,
            heading=heading,
        )

    newly_arrived = _auto_detect_arrivals(request.user, lat, lng)

    return JsonResponse({
        'success': True,
        'arrived_order_ids': newly_arrived,
        'latitude': lat,
        'longitude': lng,
    })


@require_POST
def update_customer_location(request, order_id):
    """
    Receives live GPS coordinates from the customer's browser on the
    Track Order page and updates the order's delivery_latitude and
    delivery_longitude in real time, allowing the rider to see the
    customer's live location and dynamic route.
    """
    order = get_object_or_404(Order, id=order_id)
    if not can_track_order(request, order):
        return JsonResponse({'success': False, 'error': 'Not authorized to update location for this order.'}, status=403)

    try:
        data = json.loads(request.body)
        lat = float(data['latitude'])
        lng = float(data['longitude'])
        accuracy = data.get('accuracy')
    except (KeyError, ValueError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Invalid location payload.'}, status=400)

    order.delivery_latitude = lat
    order.delivery_longitude = lng
    order.save(update_fields=['delivery_latitude', 'delivery_longitude'])

    return JsonResponse({
        'success': True,
        'latitude': lat,
        'longitude': lng,
        'accuracy': accuracy,
        'message': 'Customer live location updated successfully.'
    })


@require_GET
def order_location_api(request, order_id):
    """
    Polled every few seconds by Customer Track Order & Rider Delivery pages.
    Returns:
      - Rider's live coordinates (🛵)
      - Customer's delivery location (🏠)
      - Farm/store/pickup location if available (🏪)
      - Distance between rider and customer
      - Dynamic ETA
      - Order status, Rider details, and Order details
    """
    order = get_object_or_404(Order.objects.select_related('customer', 'driver').prefetch_related('items__product__farm'), id=order_id)
    if not can_track_order(request, order):
        return JsonResponse({'success': False, 'error': 'Not authorized to track this order.'}, status=403)

    # 1. Customer Delivery Location
    customer_lat = float(order.delivery_latitude) if order.delivery_latitude is not None else None
    customer_lng = float(order.delivery_longitude) if order.delivery_longitude is not None else None

    # Fallback to Chennai center default if completely unset, to ensure map always renders pin
    if customer_lat is None or customer_lng is None:
        customer_lat = 13.050000
        customer_lng = 80.212000

    # 2. Farm / Store / Pickup Location
    farm_lat = order.pickup_latitude
    farm_lng = order.pickup_longitude
    if farm_lat is None or farm_lng is None:
        farm_lat = 13.082700
        farm_lng = 80.270700

    farm_info = {
        'name': order.pickup_farm_name,
        'address': order.pickup_farm.location if order.pickup_farm and order.pickup_farm.location else 'Fresh Trace Central Farm Hub',
        'latitude': farm_lat,
        'longitude': farm_lng,
    }

    # 3. Rider Location
    rider_info = None
    dist_m = 0
    eta_mins = 0
    eta_display = "Calculating..."
    eta_iso = None

    if order.driver:
        try:
            loc = order.driver.location
            rider_lat = float(loc.latitude)
            rider_lng = float(loc.longitude)
            rider_info = {
                'driver_name': order.driver.get_full_name() or order.driver.username,
                'phone': order.driver.phone_number or '',
                'latitude': rider_lat,
                'longitude': rider_lng,
                'accuracy': loc.accuracy_metres,
                'speed': loc.speed,
                'heading': loc.heading,
                'updated_at': loc.updated_at.isoformat(),
            }

            # Calculate live distance & ETA between rider and customer
            dist_m = _distance_metres(rider_lat, rider_lng, customer_lat, customer_lng)
            eta_mins, eta_display, eta_iso = _calculate_eta(dist_m, loc.speed * 3.6 if (loc.speed and loc.speed > 2) else 25.0)

        except DriverLocation.DoesNotExist:
            rider_lat = customer_lat + 0.015
            rider_lng = customer_lng + 0.015
            rider_info = {
                'driver_name': order.driver.get_full_name() or order.driver.username,
                'phone': order.driver.phone_number or '',
                'latitude': rider_lat,
                'longitude': rider_lng,
                'updated_at': None,
            }
            dist_m = _distance_metres(rider_lat, rider_lng, customer_lat, customer_lng)
            eta_mins, eta_display, eta_iso = _calculate_eta(dist_m, 25.0)
    else:
        # No driver assigned yet — default rider standby position
        rider_lat = customer_lat + 0.015
        rider_lng = customer_lng + 0.015
        rider_info = {
            'driver_name': 'Assigning Rider...',
            'phone': '',
            'latitude': rider_lat,
            'longitude': rider_lng,
            'updated_at': None,
        }
        dist_m = _distance_metres(rider_lat, rider_lng, customer_lat, customer_lng)
        eta_mins, eta_display, eta_iso = _calculate_eta(dist_m, 25.0)

    dist_display = f"{dist_m / 1000:.1f} km" if dist_m >= 1000 else f"{int(dist_m)} m"

    payload = {
        'success': True,
        'order_id': order.id,
        'order_number': f"#{order.id}",
        'status': order.status,
        'status_display': order.get_status_display(),
        'estimated_delivery_time': eta_iso or (order.estimated_delivery_time.isoformat() if order.estimated_delivery_time else None),
        'customer': {
            'name': order.customer.get_full_name() or order.customer.username,
            'phone': order.delivery_phone,
            'address': order.delivery_address,
            'latitude': customer_lat,
            'longitude': customer_lng,
        },
        'pickup': farm_info,
        'rider': rider_info,
        'driver_location': rider_info,  # backwards compatibility
        'distance_metres': round(dist_m, 1),
        'distance_display': dist_display,
        'eta_minutes': eta_mins,
        'eta_display': eta_display,
        'arrived': bool(order.arrived_at),
        'otp_visible': order.is_otp_visible,
        'otp': order.delivery_otp if order.is_otp_visible else None,
        'subtotal': str(order.subtotal),
        'delivery_fee': str(order.delivery_fee),
        'total_amount': str(order.total_amount),
        'items': [
            {
                'name': item.product_name,
                'variant': item.variant_label,
                'quantity': item.quantity,
                'price': str(item.price),
                'line_total': str(item.line_total),
            }
            for item in order.items.all()
        ],
    }

    return JsonResponse(payload)

