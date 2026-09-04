"""
Cart (AJAX), Checkout, and Order views.

AJAX endpoints (add_to_cart, update_quantity, remove_from_cart) return
JSON so cart.js can update the page without a full reload — per the
"Add to Cart with AJAX and +/- quantity without refresh" requirement.
"""
import json
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from accounts.decorators import customer_required
from inventory.models import Product, ProductVariant, LIVE_APPROVED_PRODUCT_Q
from .access import can_track_order, grant_guest_access, normalize_phone
from .cart import Cart, product_key, variant_key
from .forms import CheckoutForm, TrackOrderLookupForm
from .models import Order, OrderItem, Cart as DBCart, CartItem
from .services import try_auto_assign, cancel_order


MAX_CART_QUANTITY = 999  # hard ceiling on quantity per cart line


def _quantity_error(requested_total, stock_quantity):
    """
    Returns an error message if requested_total isn't allowed, or None if
    it's fine. Nothing here adjusts the number — it's reject-or-allow only.
    """
    if stock_quantity is not None and requested_total > stock_quantity:
        if stock_quantity <= 0:
            return 'This product is out of stock.'
        return f'Only {stock_quantity} in stock.'
    if requested_total > MAX_CART_QUANTITY:
        return f'Maximum quantity per order is {MAX_CART_QUANTITY}.'
    return None


def cart_detail_view(request):
    cart = Cart(request)
    return render(request, 'store/cart.html', {
        'cart_items': cart.get_items(),
        'cart_subtotal': cart.get_subtotal(),
    })


def get_user_or_session_cart(request):
    """
    Retrieves or creates a database-backed Cart instance tied to the logged-in user
    or the current anonymous session.
    """
    if not request.session.session_key:
        request.session.create()
    session_key = request.session.session_key

    if request.user.is_authenticated:
        cart, _ = DBCart.objects.get_or_create(user=request.user)
        # Migrate any anonymous session cart items to the authenticated user's cart
        if session_key:
            guest_carts = DBCart.objects.filter(session_key=session_key, user__isnull=True).exclude(pk=cart.pk)
            for g_cart in guest_carts:
                for g_item in g_cart.items.all():
                    item, created = CartItem.objects.get_or_create(
                        cart=cart,
                        variant=g_item.variant,
                        defaults={'quantity': g_item.quantity}
                    )
                    if not created:
                        item.quantity += g_item.quantity
                        item.save(update_fields=['quantity'])
                g_cart.delete()
    else:
        cart, _ = DBCart.objects.get_or_create(session_key=session_key, user__isnull=True)
    return cart


@require_POST
def add_to_cart(request):
    """
    POST /cart/add/
    Payload: { variant_id: int, quantity: int } via form data or JSON.
    Validates stock availability, creates/updates the CartItem,
    and returns JSON with the updated cart item count and cart total.
    """
    variant_id = request.POST.get('variant_id')
    quantity_str = request.POST.get('quantity', 1)

    # Support JSON payload if sent as application/json
    if not variant_id and request.body:
        try:
            data = json.loads(request.body.decode('utf-8'))
            variant_id = data.get('variant_id')
            quantity_str = data.get('quantity', 1)
        except Exception:
            pass

    if not variant_id:
        return JsonResponse({'success': False, 'error': 'variant_id is required.'}, status=400)

    try:
        quantity = int(quantity_str)
        if quantity < 1:
            quantity = 1
    except (ValueError, TypeError):
        quantity = 1

    try:
        variant = ProductVariant.objects.select_related('product').get(pk=variant_id, is_active=True)
    except ProductVariant.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Selected variant does not exist or is inactive.'}, status=404)

    # Check stock availability
    if variant.stock_quantity <= 0:
        return JsonResponse({'success': False, 'error': 'This item is out of stock.'}, status=400)

    cart = get_user_or_session_cart(request)
    cart_item, created = CartItem.objects.get_or_create(
        cart=cart,
        variant=variant,
        defaults={'quantity': 0}
    )

    requested_total = cart_item.quantity + quantity
    if requested_total > variant.stock_quantity:
        return JsonResponse({
            'success': False,
            'error': f'Only {variant.stock_quantity} unit(s) available in stock. You already have {cart_item.quantity} in your cart.',
            'available_stock': variant.stock_quantity
        }, status=400)

    cart_item.quantity = requested_total
    cart_item.save(update_fields=['quantity', 'updated_at'])

    # Also keep session-based cart in sync for backward compatibility
    session_cart = Cart(request)
    session_cart.set_quantity(variant_key(variant.id), requested_total)

    cart_count = cart.total_items
    cart_total = cart.total_price

    return JsonResponse({
        'success': True,
        'status': 'ok',
        'message': f'{variant.product.name} ({variant.label}) added to cart.',
        'cart_count': cart_count,
        'cart_total': f'{cart_total:.2f}',
        'item': {
            'variant_id': variant.id,
            'product_name': variant.product.name,
            'variant_label': variant.label,
            'quantity': cart_item.quantity,
            'unit_price': str(variant.price),
            'line_total': f'{cart_item.total_price:.2f}',
        }
    })



@require_POST
def add_to_cart_ajax(request, product_id):
    """
    AJAX: add one unit (or POSTed quantity) of a product to the cart.
    If the product sells by size (product.has_variants), a variant_id
    POST param is required — you can't add a variant-having product by
    its base price, only by a specific size.
    """
    product = get_object_or_404(Product.objects.filter(LIVE_APPROVED_PRODUCT_Q), id=product_id, is_active=True)
    try:
        quantity = int(request.POST.get('quantity', 1))
    except (TypeError, ValueError):
        quantity = 1
    quantity = max(1, quantity)

    if product.has_variants:
        variant_id = request.POST.get('variant_id')
        if variant_id:
            variant = get_object_or_404(ProductVariant, id=variant_id, product=product, is_active=True)
        else:
            variant = product.variants.filter(is_active=True, stock_quantity__gt=0).first() or product.variants.filter(is_active=True).first()
        if variant is None:
            return JsonResponse({'success': False, 'error': 'This product has no active size options.'}, status=400)
        key = variant_key(variant.id)
        stock = variant.stock_quantity
        display_name = f'{product.name} ({variant.label})'
    else:
        key = product_key(product.id)
        stock = product.stock_quantity
        display_name = product.name

    cart = Cart(request)
    current_qty = cart.cart.get(key, 0)
    requested_total = current_qty + quantity

    error = _quantity_error(requested_total, stock)
    if error:
        return JsonResponse({'success': False, 'error': error}, status=400)

    cart.set_quantity(key, requested_total)
    items_data = [
        {
            'key': item['key'],
            'name': item['name'],
            'unit_price': str(item['unit_price']),
            'quantity': item['quantity'],
            'line_total': str(item['line_total']),
            'image_url': item.get('image_url') or '',
            'farm_name': item.get('farm_name') or '',
            'farm_location': item.get('farm_location') or '',
        }
        for item in cart.get_items()
    ]
    return JsonResponse({
        'success': True,
        'status': 'ok',
        'message': f'{display_name} added to cart.',
        'cart_count': len(cart),
        'cart_subtotal': str(cart.get_subtotal()),
        'items': items_data,
        'quantity': requested_total,
    })


@require_POST
def update_quantity_ajax(request, item_key):
    """
    AJAX: set the exact quantity for a cart line — used by the +/- buttons.
    item_key is the cart's own line key ('p5' or 'v12'), passed through
    from the cart page rather than a bare product id, so it works for
    both plain products and variants.
    action = 'increase' | 'decrease' | otherwise treated as an absolute set.
    Over-limit requests are rejected with an error, not silently adjusted.
    """
    cart = Cart(request)
    action = request.POST.get('action')
    current_qty = cart.cart.get(item_key, 0)

    if item_key.startswith('v'):
        line_obj = get_object_or_404(ProductVariant, id=item_key[1:])
        stock = line_obj.stock_quantity
    else:
        line_obj = get_object_or_404(Product, id=item_key[1:])
        stock = line_obj.stock_quantity

    if action == 'increase':
        new_qty = current_qty + 1
    elif action == 'decrease':
        new_qty = current_qty - 1
    else:
        try:
            new_qty = int(request.POST.get('quantity', current_qty))
        except (TypeError, ValueError):
            new_qty = current_qty

    if new_qty > current_qty:  # only growing the quantity needs a limit check
        error = _quantity_error(new_qty, stock)
        if error:
            return JsonResponse({'success': False, 'error': error}, status=400)

    cart.set_quantity(item_key, new_qty)

    unit_price = line_obj.price
    line_total = unit_price * cart.cart.get(item_key, 0)

    items_data = [
        {
            'key': item['key'],
            'name': item['name'],
            'unit_price': str(item['unit_price']),
            'quantity': item['quantity'],
            'line_total': str(item['line_total']),
            'image_url': item.get('image_url') or '',
            'farm_name': item.get('farm_name') or '',
            'farm_location': item.get('farm_location') or '',
        }
        for item in cart.get_items()
    ]

    return JsonResponse({
        'success': True,
        'quantity': cart.cart.get(item_key, 0),
        'line_total': str(line_total),
        'cart_count': len(cart),
        'cart_subtotal': str(cart.get_subtotal()),
        'items': items_data,
        'removed': item_key not in cart.cart,
    })


@require_POST
def remove_from_cart_ajax(request, item_key):
    cart = Cart(request)
    cart.remove(item_key)
    items_data = [
        {
            'key': item['key'],
            'name': item['name'],
            'unit_price': str(item['unit_price']),
            'quantity': item['quantity'],
            'line_total': str(item['line_total']),
            'image_url': item.get('image_url') or '',
            'farm_name': item.get('farm_name') or '',
            'farm_location': item.get('farm_location') or '',
        }
        for item in cart.get_items()
    ]
    return JsonResponse({
        'success': True,
        'cart_count': len(cart),
        'cart_subtotal': str(cart.get_subtotal()),
        'items': items_data,
    })



@login_required
@customer_required
def checkout_view(request):
    cart = Cart(request)
    if len(cart) == 0:
        messages.warning(request, 'Your cart is empty.')
        return redirect('orders:cart_detail')

    if request.method == 'POST':
        form = CheckoutForm(request.POST)
        if form.is_valid():
            cart_items = cart.get_items()

            # Re-check stock right before committing — protects against the
            # stock having changed (other orders, admin edits) since items
            # were added to the cart.
            insufficient = [item for item in cart_items if item['quantity'] > item['stock_quantity']]
            if insufficient:
                names = ', '.join(i['name'] for i in insufficient)
                messages.error(request, f'Sorry, stock changed for: {names}. Please review your cart.')
                return redirect('orders:cart_detail')

            with transaction.atomic():
                order = form.save(commit=False)
                order.customer = request.user
                order.status = Order.Status.PENDING
                order.save()

                for item in cart_items:
                    OrderItem.objects.create(
                        order=order,
                        product=item['product'],
                        variant=item['variant'],
                        product_name=item['product'].name,
                        variant_label=item['variant'].label if item['variant'] else '',
                        price=item['unit_price'],
                        quantity=item['quantity'],
                    )
                    # This is what makes Admin Inventory reflect reality —
                    # stock is only actually committed once an order exists,
                    # not just because something's sitting in a cart.
                    if item['variant']:
                        ProductVariant.objects.filter(pk=item['variant'].pk).update(
                            stock_quantity=F('stock_quantity') - item['quantity']
                        )
                    else:
                        Product.objects.filter(pk=item['product'].pk).update(
                            stock_quantity=F('stock_quantity') - item['quantity']
                        )
                order.recalculate_total()

            cart.clear()

            if try_auto_assign(order):
                messages.success(
                    request,
                    f'Order #{order.pk} placed successfully! '
                    f'A driver ({order.driver.username}) has been assigned to your delivery.'
                )
            else:
                messages.success(
                    request,
                    f'Order #{order.pk} placed successfully! '
                    f'A driver will be assigned shortly.'
                )

            # Trigger WhatsApp Order Confirmation (safely isolated so errors never block checkout)
            try:
                from whatsapp_webhook.services import send_order_confirmation
                send_order_confirmation(order)
            except Exception:
                import logging
                logging.getLogger(__name__).exception("WhatsApp order confirmation failed for Order #%s", order.pk)

            return redirect('orders:my_orders')


        messages.error(request, 'Please correct the errors below.')
    else:
        initial = {'delivery_address': request.user.address, 'delivery_phone': request.user.phone_number}
        form = CheckoutForm(initial=initial)

    return render(request, 'store/checkout.html', {
        'form': form,
        'cart_items': cart.get_items(),
        'cart_subtotal': cart.get_subtotal(),
    })


@login_required
@customer_required
def my_orders_view(request):
    orders = Order.objects.filter(customer=request.user).prefetch_related('items')
    return render(request, 'store/my_orders.html', {'orders': orders})


@login_required
@customer_required
@require_POST
def cancel_order_view(request, order_id):
    """
    Customer self-service cancellation. Only allowed for their own order,
    and only while it's still PENDING or CONFIRMED — once a driver has
    picked it up (OUT_FOR_DELIVERY) or it's DELIVERED, they can't cancel
    it here, since the goods are already out. Stock is given back
    automatically (see orders.services.cancel_order).
    """
    order = get_object_or_404(Order, id=order_id, customer=request.user)
    if cancel_order(order):
        messages.success(request, f'Order #{order.id} has been cancelled.')
    else:
        messages.error(request, f'Order #{order.id} can no longer be cancelled — it may already be out for delivery.')
    return redirect('orders:my_orders')


@login_required
def order_detail_view(request, order_id):
    """Order detail + entry point to live tracking (customers see their own orders; admins see any)."""
    if request.user.role == 'admin':
        order = get_object_or_404(Order, id=order_id)
    else:
        order = get_object_or_404(Order, id=order_id, customer=request.user)
    return render(request, 'store/track_order.html', {'order': order})


def track_lookup_view(request):
    """
    Public, no-login page: enter an order number + the mobile number used
    at checkout to jump straight to that order's live tracking page —
    for guests, or anyone who doesn't want to log in just to check a delivery.
    """
    if request.method == 'POST':
        form = TrackOrderLookupForm(request.POST)
        if form.is_valid():
            order = Order.objects.filter(id=form.cleaned_data['order_id']).first()
            phone_matches = order and normalize_phone(order.delivery_phone) == normalize_phone(form.cleaned_data['delivery_phone'])
            if phone_matches:
                grant_guest_access(request, order)
                return redirect('orders:track_guest', order_id=order.id)
            messages.error(request, "We couldn't find an order with that number and mobile number. Please check both and try again.")
    else:
        form = TrackOrderLookupForm()
    return render(request, 'store/track_lookup.html', {'form': form})


def track_guest_view(request, order_id):
    """
    Public tracking page for the order+phone flow above. Also works for a
    logged-in owner/admin/assigned-driver who navigates here directly —
    can_track_order() covers all of those cases in one place.
    """
    order = get_object_or_404(Order, id=order_id)
    if not can_track_order(request, order):
        messages.error(request, 'Please look up your order with its number and mobile number to track it.')
        return redirect('orders:track_lookup')
    return render(request, 'store/track_order.html', {'order': order})
