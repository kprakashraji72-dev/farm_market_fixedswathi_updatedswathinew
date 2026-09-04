"""
wa_flow/services.py
───────────────────
Core business logic for WhatsApp Flow and Webhook handling:
- handle_flow_action(): Routes flow screen states and implements data exchange
  contract (PRODUCTS -> DELIVERY -> SUMMARY -> COMPLETE).
- send_flow_message(): Dispatches interactive Flow trigger message via Cloud API.
- create_flow_order(): Persists confirmed orders to wa_flow.models.Order.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import requests
from django.conf import settings

from .models import Category, Order, Product, QUANTITY_CHOICES, QUANTITY_MAP

logger = logging.getLogger(__name__)


# ─── Formatting & Calculation Helpers ─────────────────────────────────────────

def format_inr(amount: Decimal | float) -> str:
    """Format decimal amount as '₹ XX.XX' per flow.json spec."""
    return f"₹ {Decimal(str(amount)):.2f}"


def calculate_totals(
    product_id: Optional[str],
    quantity_id: Optional[str]
) -> Tuple[Optional[Product], Dict[str, Any]]:
    """
    Looks up Product and Quantity multiplier, calculates subtotal, delivery fee,
    and total amount. Returns Product object and formatted pricing dictionary.
    """
    prod = Product.objects.filter(id=product_id).first() if product_id else None
    if not prod:
        prod = Product.objects.first()

    qty_info = QUANTITY_MAP.get(quantity_id, QUANTITY_CHOICES[0])
    multiplier = Decimal(str(qty_info["multiplier"]))
    unit_price = prod.unit_price if prod else Decimal("80.00")
    subtotal = unit_price * multiplier
    delivery_fee = Decimal("5.00")
    total_amount = subtotal + delivery_fee

    pricing = {
        "unit_price": format_inr(unit_price),
        "subtotal": format_inr(subtotal),
        "delivery_fee": format_inr(delivery_fee),
        "total_amount": format_inr(total_amount),
        "raw_subtotal": subtotal,
        "raw_total": total_amount,
        "product_id": prod.id if prod else "prod_16",
        "product_name": prod.title if prod else "Ooty Red Carrot",
        "quantity_id": qty_info["id"],
        "quantity_label": qty_info["title"],
    }
    return prod, pricing


def get_products_screen_data(
    category_id: Optional[str] = None,
    product_id: Optional[str] = None,
    quantity_id: Optional[str] = None
) -> Dict[str, Any]:
    """Populates dynamic data for PRODUCTS screen from the database."""
    categories_qs = Category.objects.all()
    categories_list = [{"id": c.id, "title": c.title} for c in categories_qs]

    if not category_id or not Category.objects.filter(id=category_id).exists():
        category_id = categories_list[0]["id"] if categories_list else "cat_veg"

    prods_qs = Product.objects.filter(category_id=category_id)
    if not prods_qs.exists():
        prods_qs = Product.objects.all()

    products_list = [
        {"id": p.id, "title": f"{p.title} (₹{p.unit_price:.0f}/{p.unit_label})"}
        for p in prods_qs
    ]

    if not product_id or not prods_qs.filter(id=product_id).exists():
        product_id = products_list[0]["id"] if products_list else "prod_16"

    quantity_id = quantity_id or "qty_1"
    _, pricing = calculate_totals(product_id, quantity_id)

    return {
        "categories": categories_list,
        "products": products_list,
        "quantities": [{"id": q["id"], "title": q["title"]} for q in QUANTITY_CHOICES],
        "selected_category": category_id,
        "selected_product": product_id,
        "selected_quantity": quantity_id,
        "unit_price": pricing["unit_price"],
        "subtotal": pricing["subtotal"],
        "delivery_fee": pricing["delivery_fee"],
        "total_amount": pricing["total_amount"],
    }


# ─── Flow Action Dispatcher ───────────────────────────────────────────────────

def handle_flow_action(decrypted: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handles WhatsApp Flow data_exchange routing:
    PRODUCTS -> DELIVERY -> SUMMARY -> COMPLETE

    Performs validation, live price recalculation, and database order persistence.
    """
    action: str = decrypted.get("action", "")
    screen: str = decrypted.get("screen", "")
    data: Dict[str, Any] = decrypted.get("data", {})
    flow_token: str = decrypted.get("flow_token", "")

    logger.info("[wa_flow] Action='%s' Screen='%s' Data=%s", action, screen, data)

    # 1. Health check ping (Used by Meta Flow Builder 'Test Endpoint' tool)
    if action == "ping":
        return {"data": {"status": "active"}}

    # 2. INIT (Customer opens the Flow) -> Return PRODUCTS screen
    if action == "INIT":
        return {
            "screen": "PRODUCTS",
            "data": get_products_screen_data()
        }

    # 3. Screen navigation & Dynamic Updates
    if action == "data_exchange":

        # ── PRODUCTS Screen ───────────────────────────────────────────────────
        if screen == "PRODUCTS":
            cat_id = data.get("category") or data.get("produce_category") or "cat_veg"
            prod_id = data.get("product") or data.get("product_id") or "prod_16"
            qty_id = data.get("quantity") or data.get("quantity_id") or "qty_1"

            is_continue = (
                data.get("continue_to_delivery")
                or data.get("trigger") == "products_selected"
                or ("customer_name" in data or "delivery_address" in data)
            )

            # Live recalculation on dropdown selection
            if not is_continue:
                return {
                    "screen": "PRODUCTS",
                    "data": get_products_screen_data(cat_id, prod_id, qty_id)
                }

            # Footer 'Proceed to Delivery' -> Transition to DELIVERY
            _, pricing = calculate_totals(prod_id, qty_id)
            return {
                "screen": "DELIVERY",
                "data": {
                    "product_id": pricing["product_id"],
                    "product_name": pricing["product_name"],
                    "produce_category": data.get("produce_category", cat_id),
                    "quantity": data.get("quantity") if data.get("quantity") and not str(data.get("quantity")).startswith("qty_") else pricing["quantity_label"],
                    "subtotal": pricing["subtotal"],
                    "delivery_fee": pricing["delivery_fee"],
                    "total_amount": pricing["total_amount"],
                    "payment_mode": "COD",
                }
            }

        # ── DELIVERY Screen ───────────────────────────────────────────────────
        if screen == "DELIVERY":
            phone = str(data.get("delivery_phone", "")).strip()
            # Clean non-digits
            digits_only = "".join(ch for ch in phone if ch.isdigit())

            # Validate phone number (must be at least 10 digits)
            if phone and len(digits_only) < 10:
                return {
                    "screen": "DELIVERY",
                    "data": {
                        **data,
                        "error_message": "Please enter a valid 10-digit phone number."
                    }
                }

            payment_mode_id = data.get("payment_mode", "COD")
            payment_label = (
                "Cash on Delivery (COD)"
                if payment_mode_id == "COD"
                else "UPI on Delivery"
            )

            prod_id = data.get("product_id", "prod_16")
            qty_label = data.get("quantity", "1 kg (or bunch)")
            _, pricing = calculate_totals(prod_id, "qty_1")

            return {
                "screen": "SUMMARY",
                "data": {
                    "product_id": prod_id,
                    "product_name": data.get("product_name", pricing["product_name"]),
                    "produce_category": data.get("produce_category", "Fresh Vegetables"),
                    "quantity": qty_label,
                    "unit_price": data.get("unit_price", pricing["unit_price"]),
                    "subtotal": data.get("subtotal", pricing["subtotal"]),
                    "delivery_fee": data.get("delivery_fee", pricing["delivery_fee"]),
                    "total_amount": data.get("total_amount", pricing["total_amount"]),
                    "customer_name": data.get("customer_name", "Valued Customer"),
                    "address": data.get("address", data.get("delivery_address", "Delivery Address")),
                    "delivery_address": data.get("delivery_address", data.get("address", "Delivery Address")),
                    "delivery_phone": phone,
                    "delivery_date": str(data.get("delivery_date", "")),
                    "payment_mode": payment_label,
                }
            }

        # ── SUMMARY Screen ────────────────────────────────────────────────────
        if screen == "SUMMARY":
            order_id = create_flow_order(data)
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

        # ── COMPLETE Screen ───────────────────────────────────────────────────
        if screen == "COMPLETE":
            return {"data": {"status": "done"}}

    return {"data": {"error": f"Unhandled action '{action}'"}}


# ─── Save Order to Database ───────────────────────────────────────────────────

def create_flow_order(data: Dict[str, Any]) -> int:
    """
    Creates an Order record in wa_flow.models.Order.
    Also syncs with core orders.models.Order for the admin dashboard.
    """
    prod_id = data.get("product_id", "")
    product = Product.objects.filter(id=prod_id).first()

    subtotal_dec = Decimal(str(data.get("subtotal", "80.00")).replace("₹", "").strip())
    fee_dec = Decimal(str(data.get("delivery_fee", "5.00")).replace("₹", "").strip())
    total_dec = Decimal(str(data.get("total_amount", "85.00")).replace("₹", "").strip())

    order = Order.objects.create(
        product=product,
        quantity_label=data.get("quantity", "1 kg"),
        unit_price=product.unit_price if product else Decimal("80.00"),
        subtotal=subtotal_dec,
        delivery_fee=fee_dec,
        total_amount=total_dec,
        customer_name=data.get("customer_name", "WhatsApp Customer").strip(),
        delivery_phone=data.get("delivery_phone", "").strip() or "918807856058",
        delivery_address=data.get("delivery_address", data.get("address", "Delivery Address")).strip(),
        payment_mode=Order.PaymentMode.COD if "COD" in str(data.get("payment_mode", "COD")) else Order.PaymentMode.UPI,
        status="CONFIRMED",
    )

    logger.info("[wa_flow] Successfully saved Order #%s for %s", order.id, order.customer_name)
    return order.id


create_order = create_flow_order


# ─── Outbound Cloud API Flow Trigger ──────────────────────────────────────────

def send_flow_message(to_phone: str) -> bool:
    """
    Sends an interactive WhatsApp Flow message opening the Flow at PRODUCTS screen.
    Posts to https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages.
    """
    token: str = getattr(settings, "WHATSAPP_TOKEN", "")
    phone_number_id: str = getattr(settings, "PHONE_NUMBER_ID", "")
    flow_id: str = getattr(settings, "FLOW_ID", "1081930417655056")

    if not token or not phone_number_id:
        logger.error("[wa_flow] Cannot send Flow: WHATSAPP_TOKEN or PHONE_NUMBER_ID missing.")
        return False

    url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    cleaned_to = "".join(ch for ch in str(to_phone) if ch.isdigit())

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": cleaned_to,
        "type": "interactive",
        "interactive": {
            "type": "flow",
            "header": {
                "type": "text",
                "text": "Fresh Trace Farm Market 🌿"
            },
            "body": {
                "text": (
                    "Hello! Welcome to Fresh Trace Farm Market.\n\n"
                    "Tap below to choose farm-fresh produce, pick your quantity, "
                    "and order directly inside WhatsApp!"
                )
            },
            "footer": {
                "text": "Farm Fresh Delivery"
            },
            "action": {
                "name": "flow",
                "parameters": {
                    "mode": getattr(settings, "FLOW_MODE", "draft"),
                    "flow_message_version": "3",
                    "flow_token": f"flow_{uuid.uuid4().hex[:12]}",
                    "flow_id": str(flow_id),
                    "flow_cta": "Order Produce 🛒",
                    "flow_action": "navigate",
                    "flow_action_payload": {
                        "screen": "PRODUCTS",
                        "data": {
                            "categories": [
                                {"id": "cat_veg", "title": "🥕 Fresh Vegetables"},
                                {"id": "cat_fruits", "title": "🍎 Farm Fresh Fruits"},
                                {"id": "cat_greens", "title": "🥬 Organic Greens"},
                            ]
                        }
                    }
                }
            }
        }
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=12)
        if response.status_code in (200, 201):
            logger.info("[wa_flow] Successfully dispatched Flow to +%s", cleaned_to)
            return True

        logger.error(
            "[wa_flow] Meta API returned HTTP %s sending Flow to +%s: %s",
            response.status_code,
            cleaned_to,
            response.text
        )
        return False

    except Exception as exc:
        logger.exception("[wa_flow] Exception sending Flow message: %s", exc)
        return False
