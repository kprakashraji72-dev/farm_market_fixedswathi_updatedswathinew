"""
WhatsApp Cloud API service for sending transactional template messages.
Reads credentials dynamically via python-decouple (config).
"""
import logging
import re
import sys
import requests
from decouple import config

logger = logging.getLogger(__name__)


def _safe_print_svc(text: str) -> None:
    """Print to stdout, replacing unencodable characters safely on Windows with immediate flush."""
    try:
        print(text, flush=True)
    except Exception:
        try:
            enc = sys.stdout.encoding or "utf-8"
            encoded = text.encode(enc, errors="replace").decode(enc, errors="replace")
            print(encoded, flush=True)
        except Exception:
            pass

# WhatsApp Cloud API credentials from .env
WHATSAPP_PHONE_NUMBER_ID = config("WHATSAPP_PHONE_NUMBER_ID", default="")
WHATSAPP_ACCESS_TOKEN = config("WHATSAPP_ACCESS_TOKEN", default="")
WHATSAPP_API_VERSION = config("WHATSAPP_API_VERSION", default="v21.0")
WHATSAPP_ORDER_TEMPLATE_NAME = config("WHATSAPP_ORDER_TEMPLATE_NAME", default="jaspers_market_order_confirmation_v1")
WHATSAPP_ORDER_TEMPLATE_LANG = config("WHATSAPP_ORDER_TEMPLATE_LANG", default="en_US")


def normalize_phone_number(phone: str, default_country_code: str = "91") -> str:
    """
    Normalizes a phone number to WhatsApp international digits-only format (e.g. 919876543210).
    Strips '+', spaces, dashes, parentheses, etc.
    """
    if not phone:
        return ""
    digits = re.sub(r"\D", "", str(phone))
    
    # If 10 digits provided (standard Indian mobile format without country code), prepend default_country_code
    if len(digits) == 10 and default_country_code:
        digits = f"{default_country_code}{digits}"
    
    return digits


def _send_template_message(
    to_phone: str,
    template_name: str,
    language_code: str = "en_US",
    body_parameters: list = None,
    button_parameter: str = None
) -> dict:
    """
    Sends a pre-approved template message via the Meta WhatsApp Cloud API.
    """
    phone_id = config("WHATSAPP_PHONE_NUMBER_ID", default="")
    token = config("WHATSAPP_ACCESS_TOKEN", default="")
    api_version = config("WHATSAPP_API_VERSION", default="v21.0")

    if not phone_id or not token:
        logger.warning(
            "[WhatsApp] Skipping message send: WHATSAPP_PHONE_NUMBER_ID or WHATSAPP_ACCESS_TOKEN is missing in .env"
        )
        print("\n[WHATSAPP] [WARN] Missing WHATSAPP_PHONE_NUMBER_ID or WHATSAPP_ACCESS_TOKEN in .env")
        return {"success": False, "error": "WhatsApp credentials not configured in .env"}

    normalized_to = normalize_phone_number(to_phone)
    if not normalized_to:
        logger.warning("[WhatsApp] Skipping message send: recipient phone number is empty or invalid.")
        print("\n[WHATSAPP] [WARN] Invalid recipient phone number provided.")
        return {"success": False, "error": "Invalid recipient phone number"}

    url = f"https://graph.facebook.com/{api_version}/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # Assemble template components (hello_world template takes no components)
    components = []
    
    if template_name.lower() != "hello_world":
        # Body parameters
        if body_parameters:
            components.append({
                "type": "body",
                "parameters": [{"type": "text", "text": str(param)} for param in body_parameters]
            })

        # Optional dynamic button parameter if button URL contains {{1}}
        if button_parameter:
            components.append({
                "type": "button",
                "sub_type": "url",
                "index": "0",
                "parameters": [{"type": "text", "text": str(button_parameter)}]
            })

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": normalized_to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {
                "code": language_code
            },
        }
    }
    
    if components:
        payload["template"]["components"] = components

    print("\n" + "=" * 60)
    print(" [META WHATSAPP DISPATCH]")
    print(f" -> Recipient: +{normalized_to}")
    print(f" -> Template:  {template_name} ({language_code})")
    if body_parameters and template_name.lower() != "hello_world":
        print(f" -> Variables: {body_parameters}")
    print("=" * 60)

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=25)
        resp_data = response.json()
        
        if response.status_code in (200, 201):
            msg_id = resp_data.get('messages', [{}])[0].get('id', '')
            print(f"[WHATSAPP] [OK] Message sent successfully! Message ID: {msg_id}\n")
            logger.info(
                "[WhatsApp] Template '%s' sent successfully to +%s: %s",
                template_name, normalized_to, resp_data
            )
            return {"success": True, "data": resp_data}
        else:
            error_msg = resp_data.get('error', {}).get('message', 'Unknown error')
            print(f"[WHATSAPP] [ERROR] Failed to send template (HTTP {response.status_code}): {error_msg}\n")
            logger.error(
                "[WhatsApp] Failed to send template '%s' to +%s. Status: %s, Response: %s",
                template_name, normalized_to, response.status_code, resp_data
            )
            return {"success": False, "status_code": response.status_code, "error": resp_data}

    except Exception as e:
        print(f"[WHATSAPP] [ERROR] Exception during dispatch: {e}\n")
        logger.exception("[WhatsApp] Exception occurred while sending template '%s' to +%s: %s", template_name, normalized_to, e)
        return {"success": False, "error": str(e)}


def send_order_confirmation(order, button_dynamic: bool = False) -> dict:
    """
    Sends the approved WhatsApp order confirmation template to the customer.
    Defaults to 'jaspers_market_order_confirmation_v1' (or 'hello_world' fallback).
    Automatically registers/updates a WhatsAppFollowUp tracking record.
    """
    from .models import WhatsAppFollowUp
    from django.utils import timezone

    try:
        template_name = config("WHATSAPP_ORDER_TEMPLATE_NAME", default="jaspers_market_order_confirmation_v1")
        language_code = config("WHATSAPP_ORDER_TEMPLATE_LANG", default="en_US")

        # 1. Resolve recipient phone number
        to_phone = getattr(order, "delivery_phone", "") or (
            order.customer.phone_number if getattr(order, "customer", None) and hasattr(order.customer, "phone_number") else ""
        )
        if not to_phone:
            logger.warning("[WhatsApp] Cannot send order confirmation for Order #%s: No phone number found.", getattr(order, "pk", "Unknown"))
            print(f"[WHATSAPP] [WARN] No phone number on Order #{getattr(order, 'pk', 'Unknown')} or customer profile.")
            return {"success": False, "error": "No phone number on order or customer profile."}

        # 2. Extract Customer Name ({{1}})
        customer_name = "Customer"
        if getattr(order, "customer", None):
            customer_name = (
                getattr(order.customer, "first_name", "")
                or (order.customer.get_full_name() if hasattr(order.customer, "get_full_name") else "")
                or getattr(order.customer, "username", "")
                or "Customer"
            )

        # 3. Extract Order Number ({{2}})
        order_number = str(order.pk)

        # 4. Extract Estimated Delivery ({{3}})
        if getattr(order, "estimated_delivery_time", None) and order.estimated_delivery_time:
            estimated_delivery = order.estimated_delivery_time.strftime("%A, %b %d, %Y")
        else:
            estimated_delivery = "2-3 business days"

        button_param = str(order.pk) if button_dynamic else None
        body_params = [customer_name, order_number, estimated_delivery]

        logger.info(
            "[WhatsApp] Dispatching order confirmation for Order #%s to +%s with params: %s",
            order.pk, to_phone, body_params
        )

        res = _send_template_message(
            to_phone=to_phone,
            template_name=template_name,
            language_code=language_code,
            body_parameters=body_params,
            button_parameter=button_param
        )

        # If custom order template fails, fall back to hello_world to ensure the customer is notified
        if not res.get("success") and template_name.lower() != "hello_world":
            print("[WHATSAPP] [INFO] Primary order template failed, attempting hello_world fallback...")
            res = _send_template_message(
                to_phone=to_phone,
                template_name="hello_world",
                language_code="en_US"
            )

        # Record in WhatsAppFollowUp for dashboard tracking
        try:
            normalized_to = normalize_phone_number(to_phone)
            WhatsAppFollowUp.objects.update_or_create(
                related_order=order,
                defaults={
                    'customer_name': customer_name,
                    'phone_number': normalized_to,
                    'interactive_message_sent_at': timezone.now(),
                    'customer_replied': False,
                    'followup_template_sent': False,
                }
            )
        except Exception as track_err:
            logger.warning("Error creating WhatsAppFollowUp tracking row: %s", track_err)

        return res

    except Exception as exc:
        print(f"[WHATSAPP] [ERROR] Unexpected error in send_order_confirmation for Order #{getattr(order, 'pk', 'Unknown')}: {exc}")
        logger.exception("[WhatsApp] Unexpected error in send_order_confirmation for Order #%s: %s", getattr(order, 'pk', 'Unknown'), exc)
        return {"success": False, "error": str(exc)}


def send_out_for_delivery_notification(order) -> dict:
    """
    Sends a rich WhatsApp notification to the customer when the rider clicks
    'Pick Up Order', sharing the rider's name, phone number, and live tracking map link.
    """
    try:
        to_phone = getattr(order, "delivery_phone", "") or (
            order.customer.phone_number if getattr(order, "customer", None) and hasattr(order.customer, "phone_number") else ""
        )
        if not to_phone:
            logger.warning("[WhatsApp] Cannot send out-for-delivery message for Order #%s: No phone number found.", getattr(order, 'pk', 'Unknown'))
            return {"success": False, "error": "No phone number found"}

        # Extract Rider Details
        rider_name = "Fresh Trace Fleet Rider"
        rider_phone = ""
        if order.driver:
            rider_name = order.driver.get_full_name() or order.driver.username
            rider_phone = getattr(order.driver, "phone_number", "") or ""

        # Customer Name
        customer_name = "Customer"
        if getattr(order, "customer", None):
            customer_name = getattr(order.customer, "first_name", "") or order.customer.get_full_name() or "Customer"

        domain = config("SITE_URL", default="https://upon-washday-aerobics.ngrok-free.dev").rstrip("/")
        track_url = f"{domain}/orders/track/order/{order.id}/"

        phone_display = f" ({rider_phone})" if rider_phone else ""

        body_text = (
            f"🛵 *ORDER PICKED UP & OUT FOR DELIVERY!*\n"
            f"====================================\n"
            f"📦 *Order ID:* #{order.id}\n"
            f"👤 *Customer:* {customer_name}\n\n"
            f"🛵 *DELIVERY PARTNER DETAILS:*\n"
            f"• *Name:* {rider_name}\n"
            f"• *Phone:* {rider_phone or 'Available on live map'}\n\n"
            f"📍 Your delivery partner has picked up your fresh farm items and is on the way to your location.\n\n"
            f"🚚 *Track your Rider Live:*\n{track_url}\n"
            f"====================================\n"
            f"Please share your 6-digit OTP with the rider when they arrive."
        )

        buttons = [
            {"id": "action_track", "title": "🚚 Track Live Map ➡️"}
        ]

        normalized_to = normalize_phone_number(to_phone)
        print(f"\n[WHATSAPP] Dispatching Pick Up / Out for Delivery notification to customer +{normalized_to} with Rider details ({rider_name})...")

        # 1. Attempt interactive button message
        res = send_interactive_buttons(
            to_phone=normalized_to,
            body_text=body_text,
            buttons=buttons,
            header_text=f"🛵 Order #{order.id} In Transit",
            footer_text="Fresh Trace Delivery"
        )

        # 2. Fallback to free-form text message if buttons fail
        if not res.get("success"):
            res = send_text_reply(to_phone=to_phone, message_text=body_text)

        # 3. Fallback to pre-approved template if outside 24h conversation window
        if not res.get("success"):
            res = _send_template_message(
                to_phone=to_phone,
                template_name=config("WHATSAPP_DELIVERY_TEMPLATE_NAME", default="hello_world"),
                language_code=config("WHATSAPP_DELIVERY_TEMPLATE_LANG", default="en_US")
            )

        return res

    except Exception as exc:
        logger.exception("[WhatsApp] Error sending out-for-delivery message for Order #%s: %s", getattr(order, 'pk', 'Unknown'), exc)
        return {"success": False, "error": str(exc)}


def send_delivery_otp_matched_confirmation(order, is_out_for_delivery: bool = False) -> dict:
    """
    Sends the WhatsApp delivery completion or out-for-delivery template (e.g. 'hello_world')
    to the customer.
    """
    try:
        template_name = config("WHATSAPP_DELIVERY_TEMPLATE_NAME", default="hello_world")
        language_code = config("WHATSAPP_DELIVERY_TEMPLATE_LANG", default="en_US")

        # 1. Resolve recipient phone number
        to_phone = getattr(order, "delivery_phone", "") or (
            order.customer.phone_number if getattr(order, "customer", None) and hasattr(order.customer, "phone_number") else ""
        )
        if not to_phone:
            logger.warning("[WhatsApp] Cannot send delivery notification for Order #%s: No phone number found.", getattr(order, "pk", "Unknown"))
            print(f"[WHATSAPP] [WARN] No phone number on Order #{getattr(order, 'pk', 'Unknown')} or customer profile.")
            return {"success": False, "error": "No phone number on order or customer profile."}

        event_label = "Out for Delivery" if is_out_for_delivery else "Delivery Completed / OTP Matched"
        print(f"\n[WHATSAPP] Dispatching {event_label} notification for Order #{order.pk}...")

        logger.info(
            "[WhatsApp] Dispatching %s for Order #%s to +%s (Template: %s, Lang: %s)",
            event_label, order.pk, to_phone, template_name, language_code
        )

        return _send_template_message(
            to_phone=to_phone,
            template_name=template_name,
            language_code=language_code,
            body_parameters=None,
            button_parameter=None
        )

    except Exception as exc:
        print(f"[WHATSAPP] [ERROR] Unexpected error in delivery notification for Order #{getattr(order, 'pk', 'Unknown')}: {exc}")
        logger.exception("[WhatsApp] Unexpected error in delivery notification for Order #%s: %s", getattr(order, 'pk', 'Unknown'), exc)
        return {"success": False, "error": str(exc)}


def send_interactive_message(
    order_or_recipient,
    body_text: str = "Thank you for ordering with Fresh Trace! How was your fresh farm harvest delivery? Tap below to share feedback or re-order fresh produce:",
    buttons: list = None,
    create_followup: bool = True
) -> dict:
    """
    Sends an interactive quick-reply message via Meta WhatsApp Cloud API
    and starts follow-up tracking by creating a WhatsAppFollowUp record.
    """
    from django.utils import timezone
    from .models import WhatsAppFollowUp

    phone_id = config("WHATSAPP_PHONE_NUMBER_ID", default="")
    token = config("WHATSAPP_ACCESS_TOKEN", default="")
    api_version = config("WHATSAPP_API_VERSION", default="v21.0")

    order = None
    customer_name = "Customer"
    to_phone = ""

    # Extract customer details and phone number
    if hasattr(order_or_recipient, "delivery_phone") or hasattr(order_or_recipient, "customer"):
        order = order_or_recipient
        to_phone = getattr(order, "delivery_phone", "") or (
            order.customer.phone_number if getattr(order, "customer", None) and hasattr(order.customer, "phone_number") else ""
        )
        if getattr(order, "customer", None):
            customer_name = (
                order.customer.first_name
                or order.customer.get_full_name()
                or order.customer.username
                or "Customer"
            )
    elif hasattr(order_or_recipient, "phone_number"):
        customer = order_or_recipient
        to_phone = customer.phone_number
        customer_name = getattr(customer, "first_name", "") or getattr(customer, "username", "Customer")
    elif isinstance(order_or_recipient, str):
        to_phone = order_or_recipient

    normalized_to = normalize_phone_number(to_phone)
    if not normalized_to:
        print("[WHATSAPP] [WARN] Cannot send interactive message: invalid or missing phone number.")
        return {"success": False, "error": "Invalid or missing phone number"}

    if not buttons:
        buttons = ["Re-order Fresh", "Rate Experience", "Contact Support"]

    # Build interactive quick-reply button payload (up to 3 buttons)
    action_buttons = []
    for idx, btn_text in enumerate(buttons[:3], start=1):
        action_buttons.append({
            "type": "reply",
            "reply": {
                "id": f"btn_{idx}",
                "title": str(btn_text)[:20]
            }
        })

    interactive_payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": normalized_to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": body_text
            },
            "action": {
                "buttons": action_buttons
            }
        }
    }

    url = f"https://graph.facebook.com/{api_version}/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    print("\n" + "=" * 60)
    print(" [META WHATSAPP INTERACTIVE DISPATCH]")
    print(f" -> Recipient: +{normalized_to}")
    print(f" -> Buttons:   {[b['reply']['title'] for b in action_buttons]}")
    print(f" -> Body:      {body_text}")
    print("=" * 60)

    dispatch_result = None
    try:
        response = requests.post(url, headers=headers, json=interactive_payload, timeout=25)
        resp_data = response.json()
        
        if response.status_code in (200, 201):
            msg_id = resp_data.get('messages', [{}])[0].get('id', '')
            print(f"[WHATSAPP] [OK] Interactive message sent! ID: {msg_id}\n")
            dispatch_result = {"success": True, "data": resp_data}
        else:
            error_msg = resp_data.get('error', {}).get('message', 'Unknown error')
            print(f"[WHATSAPP] [WARN] Interactive send (HTTP {response.status_code}): {error_msg}")
            # Fallback to pre-approved template if outside 24h conversation window
            template_result = _send_template_message(
                to_phone=normalized_to,
                template_name=config("WHATSAPP_DELIVERY_TEMPLATE_NAME", default="hello_world"),
                language_code=config("WHATSAPP_DELIVERY_TEMPLATE_LANG", default="en_US")
            )
            dispatch_result = template_result if template_result.get("success") else {"success": False, "error": resp_data}

    except Exception as e:
        print(f"[WHATSAPP] [ERROR] Interactive message exception: {e}\n")
        logger.exception("[WhatsApp] Interactive message exception: %s", e)
        dispatch_result = {"success": False, "error": str(e)}

    # Create WhatsAppFollowUp record to start tracking immediately
    followup = None
    if create_followup:
        followup = WhatsAppFollowUp.objects.create(
            customer_name=customer_name,
            phone_number=normalized_to,
            interactive_message_sent_at=timezone.now(),
            customer_replied=False,
            followup_template_sent=False,
            related_order=order,
        )
        print(f"[WHATSAPP FOLLOW-UP] [OK] Created Follow-Up tracking row (ID: {followup.id}) for +{normalized_to}\n")

    return {
        "success": dispatch_result.get("success", False),
        "followup_id": followup.id if followup else None,
        "followup": followup,
        "dispatch_result": dispatch_result
    }


def send_followup_reminder(followup) -> dict:
    """
    Sends the 12-hour follow-up reminder template message to the customer
    and marks followup_template_sent = True on the WhatsAppFollowUp model.
    """
    from django.utils import timezone

    template_name = config("WHATSAPP_FOLLOWUP_TEMPLATE_NAME", default=config("WHATSAPP_DELIVERY_TEMPLATE_NAME", default="hello_world"))
    language_code = config("WHATSAPP_FOLLOWUP_TEMPLATE_LANG", default=config("WHATSAPP_DELIVERY_TEMPLATE_LANG", default="en_US"))

    res = _send_template_message(
        to_phone=followup.phone_number,
        template_name=template_name,
        language_code=language_code
    )

    # Automatic fallback to pre-approved utility template if custom template fails
    if not res.get("success") and template_name.lower() != "hello_world":
        print("[WHATSAPP FOLLOW-UP] [INFO] Reminder template failed, falling back to hello_world...")
        res = _send_template_message(
            to_phone=followup.phone_number,
            template_name="hello_world",
            language_code="en_US"
        )

    if res.get("success"):
        followup.followup_template_sent = True
        followup.followup_template_sent_at = timezone.now()
        followup.save(update_fields=['followup_template_sent', 'followup_template_sent_at'])
        print(f"[WHATSAPP FOLLOW-UP] [OK] Sent reminder template to +{followup.phone_number} (Follow-Up ID: {followup.id})")
        return {"success": True, "message": f"Reminder sent to +{followup.phone_number}"}
    else:
        print(f"[WHATSAPP FOLLOW-UP] [ERROR] Failed to send reminder to +{followup.phone_number}: {res.get('error')}")
        return {"success": False, "error": res.get("error")}


# =============================================================================
# INTERACTIVE CHATBOT & MENU SERVICES
# =============================================================================

def send_interactive_buttons(
    to_phone: str,
    body_text: str,
    buttons: list,
    header_text: str = None,
    footer_text: str = "Fresh Trace 🌿"
) -> dict:
    """
    Sends a WhatsApp interactive message with up to 3 quick-reply buttons (type: 'interactive', action: 'button').
    """
    phone_id = config("WHATSAPP_PHONE_NUMBER_ID", default="")
    token = config("WHATSAPP_ACCESS_TOKEN", default="")
    api_version = config("WHATSAPP_API_VERSION", default="v21.0")

    if not phone_id or not token:
        logger.warning("[WhatsApp] Skipping interactive buttons: missing credentials in .env")
        return {"success": False, "error": "WhatsApp credentials not configured in .env"}

    normalized_to = normalize_phone_number(to_phone)
    if not normalized_to:
        logger.warning("[WhatsApp] Skipping interactive buttons: invalid recipient phone number.")
        return {"success": False, "error": "Invalid recipient phone number"}

    url = f"https://graph.facebook.com/{api_version}/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    action_buttons = []
    for btn in buttons[:3]:
        action_buttons.append({
            "type": "reply",
            "reply": {
                "id": str(btn.get("id", "btn")),
                "title": str(btn.get("title", "Select"))[:20]
            }
        })

    interactive_obj = {
        "type": "button",
        "body": {
            "text": str(body_text)[:1024]
        },
        "action": {
            "buttons": action_buttons
        }
    }
    if header_text:
        interactive_obj["header"] = {
            "type": "text",
            "text": str(header_text)[:60]
        }
    if footer_text:
        interactive_obj["footer"] = {
            "text": str(footer_text)[:60]
        }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": normalized_to,
        "type": "interactive",
        "interactive": interactive_obj
    }

    _safe_print_svc("\n" + "=" * 60)
    _safe_print_svc(" [META WHATSAPP INTERACTIVE BUTTONS DISPATCH]")
    _safe_print_svc(f" -> Recipient: +{normalized_to}")
    _safe_print_svc(f" -> Buttons:   {[b['reply']['title'] for b in action_buttons]}")
    _safe_print_svc(f" -> Body:      {str(body_text)[:120]}...")
    _safe_print_svc("=" * 60)

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=25)
        resp_data = response.json()
        if response.status_code in (200, 201):
            msg_id = resp_data.get('messages', [{}])[0].get('id', '')
            _safe_print_svc(f"[WHATSAPP] [OK] Interactive buttons sent! ID: {msg_id}\n")
            return {"success": True, "data": resp_data}
        else:
            error_msg = resp_data.get('error', {}).get('message', 'Unknown error')
            _safe_print_svc(f"[WHATSAPP] [ERROR] Interactive buttons failed: {error_msg}\n")
            return {"success": False, "error": resp_data}
    except Exception as e:
        _safe_print_svc(f"[WHATSAPP] [ERROR] Exception: {e}\n")
        return {"success": False, "error": str(e)}


def send_interactive_list(
    to_phone: str,
    header_text: str,
    body_text: str,
    button_text: str,
    sections: list
) -> dict:
    """
    Sends a WhatsApp interactive list message (type: 'interactive', action: 'list').
    """
    phone_id = config("WHATSAPP_PHONE_NUMBER_ID", default="")
    token = config("WHATSAPP_ACCESS_TOKEN", default="")
    api_version = config("WHATSAPP_API_VERSION", default="v21.0")

    if not phone_id or not token:
        logger.warning("[WhatsApp] Skipping interactive list: missing credentials in .env")
        print("\n[WHATSAPP] [WARN] Missing WHATSAPP_PHONE_NUMBER_ID or WHATSAPP_ACCESS_TOKEN in .env")
        return {"success": False, "error": "WhatsApp credentials not configured in .env"}

    normalized_to = normalize_phone_number(to_phone)
    if not normalized_to:
        logger.warning("[WhatsApp] Skipping interactive list: invalid recipient phone number.")
        print("\n[WHATSAPP] [WARN] Invalid recipient phone number provided.")
        return {"success": False, "error": "Invalid recipient phone number"}

    url = f"https://graph.facebook.com/{api_version}/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": normalized_to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {
                "type": "text",
                "text": header_text
            },
            "body": {
                "text": body_text
            },
            "footer": {
                "text": "Select an option below"
            },
            "action": {
                "button": button_text,
                "sections": sections
            }
        }
    }

    _safe_print_svc("\n" + "=" * 60)
    _safe_print_svc(" [META WHATSAPP INTERACTIVE LIST DISPATCH]")
    _safe_print_svc(f" -> Recipient: +{normalized_to}")
    _safe_print_svc(f" -> Header:    {header_text}")
    _safe_print_svc(f" -> Body:      {body_text}")
    _safe_print_svc("=" * 60)

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=25)
        resp_data = response.json()

        if response.status_code in (200, 201):
            msg_id = resp_data.get('messages', [{}])[0].get('id', '')
            _safe_print_svc(f"[WHATSAPP] [OK] Interactive list sent! ID: {msg_id}\n")
            logger.info("[WhatsApp] Interactive list sent to +%s: %s", normalized_to, resp_data)
            return {"success": True, "data": resp_data}
        else:
            error_msg = resp_data.get('error', {}).get('message', 'Unknown error')
            _safe_print_svc(f"[WHATSAPP] [ERROR] Interactive list failed ({response.status_code}): {error_msg}\n")
            logger.error("[WhatsApp] Interactive list failed for +%s: %s", normalized_to, resp_data)
            return {"success": False, "status_code": response.status_code, "error": resp_data}

    except Exception as e:
        _safe_print_svc(f"[WHATSAPP] [ERROR] Exception during interactive list dispatch: {e}\n")
        logger.exception("[WhatsApp] Exception sending interactive list to +%s: %s", normalized_to, e)
        return {"success": False, "error": str(e)}


def send_text_reply(to_phone: str, message_text: str) -> dict:
    """
    Sends a plain free-form text message (type: 'text') within the 24h conversation window.
    """
    phone_id = config("WHATSAPP_PHONE_NUMBER_ID", default="")
    token = config("WHATSAPP_ACCESS_TOKEN", default="")
    api_version = config("WHATSAPP_API_VERSION", default="v21.0")

    if not phone_id or not token:
        logger.warning("[WhatsApp] Skipping text reply: missing credentials in .env")
        _safe_print_svc("\n[WHATSAPP] [WARN] Missing WHATSAPP_PHONE_NUMBER_ID or WHATSAPP_ACCESS_TOKEN in .env")
        return {"success": False, "error": "WhatsApp credentials not configured in .env"}

    normalized_to = normalize_phone_number(to_phone)
    if not normalized_to:
        logger.warning("[WhatsApp] Skipping text reply: invalid recipient phone number.")
        _safe_print_svc("\n[WHATSAPP] [WARN] Invalid recipient phone number provided.")
        return {"success": False, "error": "Invalid recipient phone number"}

    url = f"https://graph.facebook.com/{api_version}/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": normalized_to,
        "type": "text",
        "text": {
            "body": message_text
        }
    }

    _safe_print_svc("\n" + "=" * 60)
    _safe_print_svc(" [META WHATSAPP TEXT REPLY DISPATCH]")
    _safe_print_svc(f" -> Recipient: +{normalized_to}")
    _safe_print_svc(f" -> Message:   {message_text}")
    _safe_print_svc("=" * 60)

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=25)
        resp_data = response.json()

        if response.status_code in (200, 201):
            msg_id = resp_data.get('messages', [{}])[0].get('id', '')
            _safe_print_svc(f"[WHATSAPP] [OK] Text reply sent! ID: {msg_id}\n")
            logger.info("[WhatsApp] Text reply sent to +%s: %s", normalized_to, resp_data)
            return {"success": True, "data": resp_data}
        else:
            error_msg = resp_data.get('error', {}).get('message', 'Unknown error')
            _safe_print_svc(f"[WHATSAPP] [ERROR] Text reply failed ({response.status_code}): {error_msg}\n")
            logger.error("[WhatsApp] Text reply failed for +%s: %s", normalized_to, resp_data)
            return {"success": False, "status_code": response.status_code, "error": resp_data}

    except Exception as e:
        _safe_print_svc(f"[WHATSAPP] [ERROR] Exception during text reply dispatch: {e}\n")
        logger.exception("[WhatsApp] Exception sending text reply to +%s: %s", normalized_to, e)
        return {"success": False, "error": str(e)}

# ─── Pure WhatsApp Flow Dispatch Service ─────────────────────────────────────


def send_flow_message(
    to_phone: str,
    body_text: str = "Farm Fresh Produce\n\nHandpicked organic harvest delivered fresh from local farms. Choose your item below:",
    cta_text: str = "Preview Flow",
    flow_id: str = None,
    header_text: str = "Fresh Trace Market 🌿",
    footer_text: str = "Farm Fresh Delivery"
) -> dict:
    """
    Sends an interactive WhatsApp Flow message to the recipient's phone number.
    When tapped, opens the in-app Meta Flow ('fresh_trace_market_flow').
    """
    normalized_to = normalize_phone_number(to_phone)
    if not normalized_to:
        return {"success": False, "error": "Invalid phone number"}

    resolved_flow_id = flow_id or config("WHATSAPP_FLOW_ID", default="1422173683118152")
    flow_mode = config("WHATSAPP_FLOW_MODE", default="draft").strip().lower()
    phone_id = config("WHATSAPP_PHONE_NUMBER_ID", default="")
    token = config("WHATSAPP_ACCESS_TOKEN", default="")
    api_version = config("WHATSAPP_API_VERSION", default="v21.0")

    if not phone_id or not token:
        return {"success": False, "error": "WhatsApp credentials not configured in .env"}

    api_url = f"https://graph.facebook.com/{api_version}/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    import uuid
    flow_token = f"flow_{uuid.uuid4().hex[:12]}"

    from .flow_handler import _products_screen_data

    screen_to_open = "PRODUCTS"
    initial_data = _products_screen_data()

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
                "text": body_text
            },
            "footer": {
                "text": footer_text[:60]
            },
            "action": {
                "name": "flow",
                "parameters": {
                    "mode": flow_mode,
                    "flow_message_version": "3",
                    "flow_token": flow_token,
                    "flow_id": str(resolved_flow_id),
                    "flow_cta": cta_text[:20],
                    "flow_action": "navigate",
                    "flow_action_payload": {
                        "screen": screen_to_open,
                        "data": initial_data
                    }
                }
            }
        }
    }

    try:
        print(f"\n[WHATSAPP FLOW DISPATCH] Sending Flow #{resolved_flow_id} to +{normalized_to}...")
        response = requests.post(api_url, headers=headers, json=payload, timeout=12)
        resp_data = response.json()
        if response.status_code in [200, 201]:
            print(f"[WHATSAPP FLOW] [OK] Flow message delivered! Response: {resp_data}")
            return {"success": True, "data": resp_data}
        else:
            print(f"[WHATSAPP FLOW] [ERROR] Failed to send flow (HTTP {response.status_code}): {resp_data}")
            return {"success": False, "error": resp_data}
    except Exception as e:
        logger.exception("[WhatsApp Flow] Exception sending flow message: %s", e)
        return {"success": False, "error": str(e)}
