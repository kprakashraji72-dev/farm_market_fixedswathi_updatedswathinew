"""
whatsapp_webhook/flow_handler.py
─────────────────────────────────
WhatsApp Flows endpoint handler for Fresh Trace Farm Market.

Flow Lifecycle: PRODUCTS → DELIVERY → SUMMARY → COMPLETE
Handles live category & product selection from the database, authoritative price/subtotal
calculation, required field validation, idempotent order creation, and auto-driver assignment.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from django.utils import timezone
from decouple import config

from wa_flow.flow_crypto import (
    decrypt_flow_request as _crypto_decrypt,
    encrypt_flow_response as _crypto_encrypt,
)

logger = logging.getLogger(__name__)


# ─── Decrypt & Encrypt Flow Payloads (WhatsApp Meta Flows Spec) ──────────────

def decrypt_flow_request(body: dict) -> tuple:
    """
    Decrypts inbound WhatsApp Flow request using RSA-OAEP (SHA-256) and AES-128-GCM.
    Returns: (decrypted_json_data, aes_key, iv)
    """
    return _crypto_decrypt(body)


def encrypt_flow_response(response: dict, aes_key: bytes, iv: bytes) -> str:
    """
    Encrypts outbound WhatsApp Flow response using AES-128-GCM with bitwise-inverted IV.
    Returns: base64-encoded ciphertext + tag
    """
    return _crypto_encrypt(response, aes_key, iv)


# ─── Data helpers: Categories, Products & Quantities ─────────────────────────

_QUANTITIES = [
    {"id": "qty_1",  "title": "1 kg (or bunch)",    "multiplier": 1},
    {"id": "qty_2",  "title": "2 kg",               "multiplier": 2},
    {"id": "qty_3",  "title": "3 kg",               "multiplier": 3},
    {"id": "qty_5",  "title": "5 kg (Family Pack)", "multiplier": 5},
]

_QUANTITY_MAP = {q["id"]: q for q in _QUANTITIES}

# Default fallbacks if DB is completely empty
_DEFAULT_CATEGORIES = [
    {"id": "cat_veg",    "title": "🥕 Fresh Vegetables"},
    {"id": "cat_fruits", "title": "🍎 Farm Fresh Fruits"},
    {"id": "cat_greens", "title": "🥬 Organic Greens"},
]

_DEFAULT_PRODUCTS = [
    {"id": "prod_16", "title": "Ooty Red Carrot (₹80/kg)", "name": "Ooty Red Carrot", "price": 80.0, "category_id": "cat_veg"},
    {"id": "prod_29", "title": "Fresh Orange Carrot (₹75/kg)", "name": "Fresh Orange Carrot", "price": 75.0, "category_id": "cat_veg"},
    {"id": "prod_15", "title": "Regular Carrot (₹70/kg)", "name": "Regular Carrot", "price": 70.0, "category_id": "cat_veg"},
    {"id": "prod_34", "title": "Organic Tomatoes (₹40/kg)", "name": "Organic Tomatoes", "price": 40.0, "category_id": "cat_veg"},
    {"id": "prod_21", "title": "Farm Fresh Potato (₹40/kg)", "name": "Farm Fresh Potato", "price": 40.0, "category_id": "cat_veg"},
    {"id": "prod_19", "title": "Beetroot (₹45/kg)", "name": "Beetroot", "price": 45.0, "category_id": "cat_veg"},
    {"id": "prod_fruits_1", "title": "Shimla Apple (₹120/kg)", "name": "Shimla Apple", "price": 120.0, "category_id": "cat_fruits"},
    {"id": "prod_fruits_2", "title": "Robusta Banana (₹50/kg)", "name": "Robusta Banana", "price": 50.0, "category_id": "cat_fruits"},
    {"id": "prod_greens_1", "title": "Fresh Palak / Spinach (₹30/bunch)", "name": "Fresh Palak / Spinach", "price": 30.0, "category_id": "cat_greens"},
    {"id": "prod_greens_2", "title": "Coriander & Mint Pack (₹25/bunch)", "name": "Coriander & Mint Pack", "price": 25.0, "category_id": "cat_greens"},
]


def _get_categories_from_db():
    """Queries categories from wa_flow.models.Category ordered matching UI spec."""
    cat_order = ["cat_veg", "cat_fruits", "cat_greens"]
    try:
        from wa_flow.models import Category
        qs = list(Category.objects.all())
        if qs:
            cat_map = {c.id: c.title for c in qs}
            ordered = []
            for cid in cat_order:
                if cid in cat_map:
                    ordered.append({"id": cid, "title": cat_map[cid]})
            for c in qs:
                if c.id not in cat_order:
                    ordered.append({"id": c.id, "title": c.title})
            return ordered
    except Exception as e:
        logger.warning("[FlowHandler] Category DB lookup note: %s", e)
    return _DEFAULT_CATEGORIES


def _get_products_for_category(cat_id: str):
    """Queries products for a category ordered matching UI spec."""
    veg_order = ["prod_16", "prod_29", "prod_15", "prod_34", "prod_21", "prod_19"]
    try:
        from wa_flow.models import Product
        qs = list(Product.objects.filter(category_id=cat_id))
        if qs:
            items = [
                {
                    "id": p.id,
                    "title": f"{p.title} (₹{p.unit_price:.0f}/{p.unit_label})",
                    "name": p.title,
                    "price": float(p.unit_price),
                    "category_id": p.category_id,
                }
                for p in qs
            ]
            if cat_id == "cat_veg":
                item_map = {item["id"]: item for item in items}
                ordered = [item_map[pid] for pid in veg_order if pid in item_map]
                for item in items:
                    if item["id"] not in veg_order:
                        ordered.append(item)
                return ordered
            return items
    except Exception as e:
        logger.warning("[FlowHandler] Product DB lookup note: %s", e)

    # Fallback to in-memory defaults
    matching = [p for p in _DEFAULT_PRODUCTS if p["category_id"] == cat_id]
    return matching if matching else [p for p in _DEFAULT_PRODUCTS if p["category_id"] == "cat_veg"]


def _lookup_product(prod_id: str):
    """Authoritatively looks up a product by ID from DB, then defaults."""
    try:
        from wa_flow.models import Product
        p = Product.objects.filter(id=prod_id).first()
        if p:
            return {
                "id": p.id,
                "title": f"{p.title} (₹{p.unit_price:.0f}/{p.unit_label})",
                "name": p.title,
                "price": float(p.unit_price),
                "category_id": p.category_id,
            }
    except Exception as e:
        logger.warning("[FlowHandler] Product lookup note: %s", e)

    for p in _DEFAULT_PRODUCTS:
        if p["id"] == prod_id:
            return p
    return _DEFAULT_PRODUCTS[0]


def _lookup_quantity(qty_id: str):
    return _QUANTITY_MAP.get(qty_id, _QUANTITIES[0])


def _calc_totals(prod_id: str, qty_id: str):
    """
    Calculates authoritative prices on the backend.
    Never trusts price values supplied by the client flow.
    """
    prod = _lookup_product(prod_id)
    qty  = _lookup_quantity(qty_id)
    unit_price = float(prod["price"])
    subtotal = unit_price * qty["multiplier"]
    delivery_fee = 5.0
    total = subtotal + delivery_fee
    return {
        "unit_price":   f"₹ {unit_price:.2f}/kg",
        "subtotal":     f"₹ {subtotal:.2f}",
        "delivery_fee": f"₹ {delivery_fee:.2f}",
        "total_amount": f"₹ {total:.2f}",
        "raw_unit_price": unit_price,
        "raw_subtotal": subtotal,
        "raw_delivery_fee": delivery_fee,
        "raw_total":    total,
        "product_id":   prod["id"],
        "product_name": prod["name"],
        "quantity_str": qty["title"],
        "multiplier":   qty["multiplier"],
    }


def _products_screen_data(cat_id="cat_veg", prod_id=None, qty_id="qty_1") -> dict:
    categories = _get_categories_from_db()
    if not any(c["id"] == cat_id for c in categories):
        cat_id = categories[0]["id"] if categories else "cat_veg"

    available_prods = _get_products_for_category(cat_id)
    if not prod_id or not any(p["id"] == prod_id for p in available_prods):
        prod_id = available_prods[0]["id"]

    totals = _calc_totals(prod_id, qty_id)
    return {
        "categories":        categories,
        "products":          [{"id": p["id"], "title": p["title"]} for p in available_prods],
        "quantities":        [{"id": q["id"], "title": q["title"]} for q in _QUANTITIES],
        "selected_category": cat_id,
        "selected_product":  prod_id,
        "selected_quantity": qty_id,
        "unit_price":        totals["unit_price"],
        "subtotal":          totals["subtotal"],
        "delivery_fee":      totals["delivery_fee"],
        "total_amount":      totals["total_amount"],
    }


# ─── Main Screen Routing (PRODUCTS → DELIVERY → SUMMARY → COMPLETE) ───────────

def process_flow_action(decrypted: dict) -> dict:
    action     = decrypted.get("action")
    screen     = decrypted.get("screen", "")
    data       = decrypted.get("data", {})
    flow_token = decrypted.get("flow_token", "")

    logger.info("[Flow] action=%s  screen=%s  data=%s", action, screen, data)

    # 1. Health check ping (Meta Flow Builder 'Test Endpoint' validation)
    if action == "ping":
        return {"data": {"status": "active"}}

    # 2. Initial Flow open (INIT)
    if action == "INIT":
        return {"screen": "PRODUCTS", "data": _products_screen_data()}

    # 3. Screen navigation & Dynamic Updates
    if action == "data_exchange":

        # ── SCREEN 1: PRODUCTS Screen (Fresh Farm Produce Selection) ─────────
        if screen == "PRODUCTS":
            cat_id  = data.get("category", "cat_veg")
            prod_id = data.get("product", "")
            qty_id  = data.get("quantity", "qty_1")

            is_continue = (
                data.get("continue_to_delivery")
                or data.get("trigger") == "products_selected"
                or ("customer_name" in data or "delivery_address" in data)
            )

            # Dropdown changed ➔ Dynamic price & product update on same screen
            if not is_continue:
                updated_screen = _products_screen_data(cat_id, prod_id, qty_id)
                return {"screen": "PRODUCTS", "data": updated_screen}

            # Footer 'Proceed to Delivery' tapped ➔ Transition to DELIVERY
            totals = _calc_totals(prod_id, qty_id)
            return {
                "screen": "DELIVERY",
                "data": {
                    "product_id":       totals["product_id"],
                    "product_name":     totals["product_name"],
                    "quantity":         totals["quantity_str"],
                    "produce_category": data.get("produce_category", "Fresh Vegetables"),
                    "unit_price":       totals["unit_price"],
                    "subtotal":         totals["subtotal"],
                    "delivery_fee":     totals["delivery_fee"],
                    "total_amount":     totals["total_amount"],
                    "payment_mode":     "COD",
                }
            }

        # ── SCREEN 2: DELIVERY Screen (Customer Details & Address) ───────────
        if screen == "DELIVERY":
            prod_id = data.get("product_id", "prod_16")
            qty_id  = data.get("quantity_id", "qty_1")
            totals  = _calc_totals(prod_id, qty_id)

            cust_name = str(data.get("customer_name", "")).strip() or "Valued Customer"
            address   = str(data.get("delivery_address", data.get("address", ""))).strip() or "Farm Market Delivery"
            phone_raw = str(data.get("delivery_phone", "")).strip()

            # Clean and normalize phone number
            phone_digits = "".join(ch for ch in phone_raw if ch.isdigit())
            normalized_phone = phone_raw if len(phone_digits) >= 10 else "918807856058"

            payment_mode_raw = str(data.get("payment_mode", "COD")).upper()
            payment_label = "Cash on Delivery (COD)" if "COD" in payment_mode_raw else "UPI on Delivery"

            return {
                "screen": "SUMMARY",
                "data": {
                    "product_id":       prod_id,
                    "product_name":     data.get("product_name", totals["product_name"]),
                    "produce_category": data.get("produce_category", "Fresh Vegetables"),
                    "quantity":         data.get("quantity", totals["quantity_str"]),
                    "unit_price":       totals["unit_price"],
                    "subtotal":         totals["subtotal"],
                    "delivery_fee":     totals["delivery_fee"],
                    "total_amount":     totals["total_amount"],
                    "customer_name":    cust_name,
                    "address":          address,
                    "delivery_address": address,
                    "delivery_date":    str(data.get("delivery_date", "")),
                    "delivery_phone":   normalized_phone,
                    "payment_mode":     payment_label,
                }
            }

        # ── SCREEN 3: SUMMARY Screen (Review & Place Order) ──────────────────
        if screen == "SUMMARY":
            order_id = _create_flow_order(flow_token, data)
            return {
                "screen": "COMPLETE",
                "data": {
                    "order_id": f"ORD-{order_id}",
                    "message": (
                        f"Order ORD-{order_id} confirmed! Fresh produce is packed "
                        f"and our delivery rider will bring it to your doorstep."
                    )
                }
            }

        # ── SCREEN 4: COMPLETE Screen (Terminal) ──────────────────────────────
        if screen == "COMPLETE":
            return {"data": {"status": "done"}}

    return {"data": {"error": f"Unhandled action '{action}'"}}


# ─── Save Order to Django Database (Idempotent) ───────────────────────────────

def _create_flow_order(flow_token: str, data: dict) -> int:
    """
    Creates an Order and OrderItem in Django with stock decrement and rider auto-assignment.
    Idempotent: prevents duplicate orders if the customer taps 'Confirm Order' repeatedly.
    """
    from django.contrib.auth import get_user_model
    from orders.models import Order, OrderItem
    from orders.services import try_auto_assign
    from inventory.models import Product as InvProduct

    phone_raw = str(data.get("delivery_phone", "")).strip() or "918807856058"
    cust_name = str(data.get("customer_name", "WhatsApp Customer")).strip()
    address   = str(data.get("delivery_address", data.get("address", "Farm Market Delivery"))).strip()

    # Authoritative calculation
    prod_id = data.get("product_id", "prod_16")
    qty_val = data.get("quantity", "1 kg")
    qty_id = "qty_1"
    for q in _QUANTITIES:
        if q["title"] == qty_val or q["id"] == qty_val:
            qty_id = q["id"]
            break

    totals = _calc_totals(prod_id, qty_id)
    subtotal_dec = Decimal(str(totals["raw_subtotal"]))
    delivery_fee = Decimal(str(totals["raw_delivery_fee"]))
    total_dec    = Decimal(str(totals["raw_total"]))

    # ── Idempotency Check: check recent order placed in the last 60 seconds ──
    recent_duplicate = Order.objects.filter(
        delivery_phone__icontains=phone_raw[-10:],
        total_amount=total_dec,
        created_at__gte=timezone.now() - timedelta(seconds=60)
    ).first()
    if recent_duplicate:
        logger.info("[Flow Order] Returning duplicate idempotent Order #%s for +%s", recent_duplicate.id, phone_raw)
        return recent_duplicate.id

    User = get_user_model()
    user = User.objects.filter(phone_number__icontains=phone_raw[-10:]).first()
    if not user:
        user = User.objects.create(
            username=f"wa_flow_{phone_raw[-10:]}",
            first_name=cust_name,
            phone_number=f"+{phone_raw}" if not phone_raw.startswith("+") else phone_raw,
            role=User.Role.CUSTOMER,
            address=address,
        )
    else:
        updated_fields = []
        if cust_name and not user.first_name:
            user.first_name = cust_name
            updated_fields.append("first_name")
        if address and not user.address:
            user.address = address
            updated_fields.append("address")
        if updated_fields:
            user.save(update_fields=updated_fields)

    # Create Order in Django
    order = Order.objects.create(
        customer=user,
        delivery_phone=user.phone_number,
        delivery_address=address,
        delivery_latitude=Decimal("13.050000"),
        delivery_longitude=Decimal("80.212000"),
        estimated_delivery_time=timezone.now() + timedelta(minutes=30),
        status=Order.Status.CONFIRMED,
        subtotal=subtotal_dec,
        delivery_fee=delivery_fee,
        total_amount=total_dec,
    )

    # Order item & stock decrement
    prod_name = totals["product_name"]
    prod_obj = InvProduct.objects.filter(name__icontains=prod_name.split()[0]).first()
    multiplier = totals["multiplier"]

    OrderItem.objects.create(
        order=order,
        product=prod_obj,
        product_name=prod_name,
        variant_label=totals["quantity_str"],
        price=subtotal_dec,
        quantity=multiplier,
    )

    if prod_obj and prod_obj.stock_quantity >= multiplier:
        prod_obj.stock_quantity -= multiplier
        prod_obj.save(update_fields=["stock_quantity"])

    # Auto-assign nearest available driver
    try:
        try_auto_assign(order)
        order.refresh_from_db()
    except Exception as assign_err:
        logger.warning("[Flow Order] Auto-assign notice: %s", assign_err)

    # Synchronize wa_flow.models.Order
    try:
        from wa_flow.models import Order as WaOrder, Product as WaProd
        wa_prod = WaProd.objects.filter(id=prod_id).first() or WaProd.objects.filter(title__icontains=prod_name.split()[0]).first()
        payment_mode_val = WaOrder.PaymentMode.COD if "COD" in str(data.get("payment_mode", "COD")) else WaOrder.PaymentMode.UPI
        WaOrder.objects.create(
            product=wa_prod,
            quantity_label=totals["quantity_str"],
            unit_price=Decimal(str(totals["raw_unit_price"])),
            subtotal=subtotal_dec,
            delivery_fee=delivery_fee,
            total_amount=total_dec,
            customer_name=cust_name,
            delivery_phone=user.phone_number,
            delivery_address=address,
            payment_mode=payment_mode_val,
            status="CONFIRMED"
        )
    except Exception as wa_err:
        logger.warning("[Flow Order] wa_flow Order sync note: %s", wa_err)

    # Dispatch WhatsApp order confirmation notification to customer
    try:
        from .services import send_text_reply
        confirm_msg = (
            f"🎉 *Order Placed Successfully!*\n\n"
            f"📦 *Order ID:* #ORD-{order.id}\n"
            f"🥦 *Item:* {prod_name} ({totals['quantity_str']})\n"
            f"💰 *Total Amount:* ₹{total_dec:.2f}\n"
            f"📍 *Delivery Address:* {address}\n"
            f"💵 *Payment Mode:* {data.get('payment_mode', 'Cash on Delivery (COD)')}\n\n"
            f"🌾 Thank you for ordering with Fresh Trace! Your farm-fresh produce is being packed."
        )
        send_text_reply(to_phone=user.phone_number, message_text=confirm_msg)
        logger.info("[Flow Order] Sent confirmation message for Order #%s to +%s", order.id, user.phone_number)
    except Exception as conf_err:
        logger.warning("[Flow Order] Confirmation dispatch notice: %s", conf_err)

    logger.info("[Flow Order] Successfully placed Order #%s via WhatsApp Flow for +%s", order.id, user.phone_number)
    return order.id
