"""
Session-based shopping cart. Stored as {line_key: quantity} in
request.session['cart'] so it survives across requests without needing a
DB table, and works before/after login (simplest option for this scope).

line_key format:
  'p<product_id>'  — a plain product (no size/weight variants)
  'v<variant_id>'  — a specific ProductVariant (e.g. "Tomatoes — 1kg")

Products that have variants (Product.has_variants) are always added to the
cart by variant key, never by plain product key — see orders.views.add_to_cart_ajax.
"""
from decimal import Decimal
from inventory.models import Product, ProductVariant

SESSION_KEY = 'cart'


def product_key(product_id):
    return f'p{product_id}'


def variant_key(variant_id):
    return f'v{variant_id}'


class Cart:
    def __init__(self, request):
        self.request = request
        self.session = request.session
        self.user = getattr(request, 'user', None)

        cart = self.session.get(SESSION_KEY)
        if cart is None:
            cart = self.session[SESSION_KEY] = {}
        self.cart = cart

        self._sync_with_db()

    def _sync_with_db(self):
        """
        Synchronizes session cart and database Cart model for authenticated users.
        """
        if not self.user or not self.user.is_authenticated:
            return

        try:
            from orders.models import Cart as DBCart, CartItem
            db_cart, _ = DBCart.objects.get_or_create(user=self.user)

            if not self.cart:
                # Load from database into session cart if session cart is empty
                for item in db_cart.items.select_related('variant', 'variant__product').all():
                    if item.variant and item.variant.is_active:
                        self.cart[variant_key(item.variant.id)] = item.quantity
                if self.cart:
                    self._save_session_only()
            else:
                # Sync session cart into database
                current_v_ids = set()
                for key, qty in list(self.cart.items()):
                    if key.startswith('v'):
                        try:
                            v_id = int(key[1:])
                            current_v_ids.add(v_id)
                            CartItem.objects.update_or_create(
                                cart=db_cart,
                                variant_id=v_id,
                                defaults={'quantity': qty}
                            )
                        except (ValueError, TypeError):
                            pass
                db_cart.items.exclude(variant_id__in=current_v_ids).delete()
        except Exception:
            pass

    def add(self, line_key, quantity=1):
        line_key = str(line_key)
        self.cart[line_key] = self.cart.get(line_key, 0) + quantity
        if self.cart[line_key] < 1:
            self.cart[line_key] = 1
        self._save()

    def set_quantity(self, line_key, quantity):
        line_key = str(line_key)
        if quantity <= 0:
            self.remove(line_key)
        else:
            self.cart[line_key] = quantity
            self._save()

    def remove(self, line_key):
        line_key = str(line_key)
        if line_key in self.cart:
            del self.cart[line_key]
            self._save()

    def clear(self):
        self.cart = {}
        self._save_session_only()
        if self.user and self.user.is_authenticated:
            try:
                from orders.models import Cart as DBCart
                DBCart.objects.filter(user=self.user).delete()
            except Exception:
                pass

    def _save_session_only(self):
        self.session[SESSION_KEY] = self.cart
        self.session.modified = True

    def _save(self):
        self._save_session_only()
        if self.user and self.user.is_authenticated:
            try:
                from orders.models import Cart as DBCart, CartItem
                db_cart, _ = DBCart.objects.get_or_create(user=self.user)
                current_v_ids = set()
                for key, qty in list(self.cart.items()):
                    if key.startswith('v'):
                        try:
                            v_id = int(key[1:])
                            current_v_ids.add(v_id)
                            CartItem.objects.update_or_create(
                                cart=db_cart,
                                variant_id=v_id,
                                defaults={'quantity': qty}
                            )
                        except (ValueError, TypeError):
                            pass
                db_cart.items.exclude(variant_id__in=current_v_ids).delete()
            except Exception:
                pass

    def __len__(self):
        return sum(self.cart.values())

    def get_items(self):
        """
        Returns a list of dicts for template + checkout, one per cart line:
        {key, product, variant (or None), name, unit_price, quantity,
         line_total, stock_quantity, image_url}.
        """
        product_ids = [k[1:] for k in self.cart if k.startswith('p')]
        variant_ids = [k[1:] for k in self.cart if k.startswith('v')]

        products = {str(p.id): p for p in Product.objects.select_related('farm').filter(id__in=product_ids)}
        variants = {str(v.id): v for v in ProductVariant.objects.select_related('product', 'product__farm').filter(id__in=variant_ids)}

        items = []
        for key, qty in self.cart.items():
            if key.startswith('p') and key[1:] in products:
                product = products[key[1:]]
                farm = getattr(product, 'farm', None)
                items.append({
                    'key': key,
                    'product': product,
                    'variant': None,
                    'name': product.name,
                    'unit_price': product.price,
                    'quantity': qty,
                    'line_total': product.price * qty,
                    'stock_quantity': product.stock_quantity,
                    'image_url': product.image.url if product.image else None,
                    'farm': farm,
                    'farm_name': farm.name if farm else '',
                    'farm_location': farm.location if farm else '',
                })
            elif key.startswith('v') and key[1:] in variants:
                variant = variants[key[1:]]
                prod = variant.product
                farm = getattr(prod, 'farm', None)
                items.append({
                    'key': key,
                    'product': prod,
                    'variant': variant,
                    'name': f'{prod.name} ({variant.label})',
                    'unit_price': variant.price,
                    'quantity': qty,
                    'line_total': variant.price * qty,
                    'stock_quantity': variant.stock_quantity,
                    'image_url': prod.image.url if prod.image else None,
                    'farm': farm,
                    'farm_name': farm.name if farm else '',
                    'farm_location': farm.location if farm else '',
                })
            # else: the product/variant was deleted since being added — silently skip it
        return items

    def get_subtotal(self):
        return sum(item['line_total'] for item in self.get_items()) or Decimal('0.00')

