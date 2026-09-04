"""
Global template context: cart item count for the navbar badge.
Synchronized with Cart class (session + database).
"""

def cart_summary(request):
    try:
        from orders.cart import Cart
        cart = Cart(request)
        return {
            'cart_count': len(cart),
            'nav_cart_items': cart.get_items(),
            'nav_cart_subtotal': str(cart.get_subtotal()),
        }
    except Exception:
        return {
            'cart_count': 0,
            'nav_cart_items': [],
            'nav_cart_subtotal': '0.00',
        }

