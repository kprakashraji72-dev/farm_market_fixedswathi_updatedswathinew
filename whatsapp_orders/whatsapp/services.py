"""
whatsapp/services.py
────────────────────
WhatsApp Cloud API client for sending:
1. Interactive Flow trigger messages (flow_cta="Start Order")
2. Text messages
3. Order confirmations
All calls use Graph API endpoint:
https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages
"""

import logging
import re
import uuid
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def normalize_phone_number(phone: str, default_country_code: str = "91") -> str:
    """
    Normalizes phone number to WhatsApp international digits-only format.
    E.g. '+91 88078 56058' -> '918807856058'.
    """
    if not phone:
        return ""
    digits = re.sub(r"\D", "", str(phone))
    if len(digits) == 10 and default_country_code:
        digits = f"{default_country_code}{digits}"
    return digits


def _get_api_headers() -> dict:
    token = getattr(settings, "WHATSAPP_ACCESS_TOKEN", "")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _get_messages_url() -> str:
    phone_id = getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "")
    api_version = getattr(settings, "WHATSAPP_API_VERSION", "v20.0")
    return f"https://graph.facebook.com/{api_version}/{phone_id}/messages"


def send_flow_trigger_message(
    to_phone: str,
    flow_id: str = None,
    flow_token: str = None,
    flow_cta: str = "Start Order",
    header_text: str = "Fresh Trace Market 🌿",
    body_text: str = "🛒 *Farm Fresh Produce*\n\nTap below to choose farm-fresh vegetables, fruits, and organic greens, pick your quantity, and order directly in WhatsApp!",
    footer_text: str = "Farm Fresh Delivery"
) -> dict:
    """
    Sends an interactive WhatsApp Flow message to the recipient phone number.
    Tapping the CTA button opens the in-app Flow.
    """
    normalized_to = normalize_phone_number(to_phone)
    if not normalized_to:
        logger.warning("[WhatsApp] Cannot send Flow: invalid phone number '%s'", to_phone)
        return {"success": False, "error": "Invalid phone number"}

    resolved_flow_id = flow_id or getattr(settings, "WHATSAPP_FLOW_ID", "1422173683118152")
    flow_mode = getattr(settings, "WHATSAPP_FLOW_MODE", "draft").strip().lower()
    token_val = flow_token or f"flow_{uuid.uuid4().hex[:12]}"

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": normalized_to,
        "type": "interactive",
        "interactive": {
            "type": "flow",
            "header": {
                "type": "text",
                "text": header_text[:60]
            },
            "body": {
                "text": body_text[:1024]
            },
            "footer": {
                "text": footer_text[:60]
            },
            "action": {
                "name": "flow",
                "parameters": {
                    "mode": flow_mode,
                    "flow_message_version": "3",
                    "flow_token": token_val,
                    "flow_id": str(resolved_flow_id),
                    "flow_cta": flow_cta[:20],
                    "flow_action": "navigate",
                    "flow_action_payload": {
                        "screen": "PRODUCTS"
                    }
                }
            }
        }
    }

    url = _get_messages_url()
    headers = _get_api_headers()

    try:
        logger.info("[WhatsApp] Dispatching Flow #%s to +%s (CTA: %s)", resolved_flow_id, normalized_to, flow_cta)
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        res_data = response.json()

        if response.status_code in (200, 201):
            msg_id = res_data.get("messages", [{}])[0].get("id", "")
            logger.info("[WhatsApp] Flow sent successfully! Msg ID: %s", msg_id)
            return {"success": True, "message_id": msg_id, "data": res_data, "flow_token": token_val}
        else:
            logger.error("[WhatsApp] Failed to send Flow (HTTP %s): %s", response.status_code, res_data)
            return {"success": False, "status_code": response.status_code, "error": res_data}

    except Exception as exc:
        logger.exception("[WhatsApp] Exception sending flow trigger: %s", exc)
        return {"success": False, "error": str(exc)}


def send_text_message(to_phone: str, body: str) -> dict:
    """
    Sends a plain text WhatsApp message via Meta Cloud API.
    """
    normalized_to = normalize_phone_number(to_phone)
    if not normalized_to:
        logger.warning("[WhatsApp] Cannot send text: invalid phone '%s'", to_phone)
        return {"success": False, "error": "Invalid phone number"}

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": normalized_to,
        "type": "text",
        "text": {"body": body}
    }

    url = _get_messages_url()
    headers = _get_api_headers()

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        res_data = response.json()

        if response.status_code in (200, 201):
            msg_id = res_data.get("messages", [{}])[0].get("id", "")
            logger.info("[WhatsApp] Text message sent to +%s! Msg ID: %s", normalized_to, msg_id)
            return {"success": True, "message_id": msg_id, "data": res_data}
        else:
            logger.error("[WhatsApp] Text send failed (HTTP %s): %s", response.status_code, res_data)
            return {"success": False, "status_code": response.status_code, "error": res_data}

    except Exception as exc:
        logger.exception("[WhatsApp] Exception sending text message: %s", exc)
        return {"success": False, "error": str(exc)}


def send_order_confirmation(order) -> dict:
    """
    Formats and sends the WhatsApp order confirmation message to the customer.
    """
    to_phone = getattr(order, "customer_phone", "")
    customer_name = getattr(order, "customer_name", "Valued Customer")
    prod_name = order.product.name if hasattr(order, "product") and order.product else "Farm Fresh Produce"
    quantity = getattr(order, "quantity", "1 kg")
    unit_rate = getattr(order, "unit_rate", 0.0)
    total_payable = getattr(order, "total_payable", 0.0)
    address = getattr(order, "delivery_address", "") or "Customer Address"

    message_body = (
        f"🎉 *Order Placed Successfully!*\n\n"
        f"📦 *Order ID:* #{order.pk}\n"
        f"👤 *Customer:* {customer_name}\n"
        f"🥦 *Product:* {prod_name}\n"
        f"⚖️ *Quantity:* {quantity}\n"
        f"💵 *Unit Rate:* ₹{unit_rate:.2f}\n"
        f"💰 *Total Payable:* ₹{total_payable:.2f}\n"
        f"📍 *Delivery Address:* {address}\n\n"
        f"🌾 Thank you for shopping with Fresh Trace Farm Market! Your harvest is being handpicked and prepared for delivery."
    )

    return send_text_message(to_phone=to_phone, body=message_body)
