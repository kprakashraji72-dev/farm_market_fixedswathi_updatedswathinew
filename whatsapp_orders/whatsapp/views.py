"""
whatsapp/views.py
─────────────────
Django REST Framework APIViews for WhatsApp Webhooks & Flow Data Exchange:
1. MessagesWebhookView:
   - GET /webhook/messages/ (Meta verification handshake)
   - POST /webhook/messages/ (Signature verification, keyword triggers "hi"/"hello"/"start"/"order")
2. FlowDataExchangeView:
   - POST /webhook/flow-data-exchange/ (RSA-OAEP + AES-GCM encrypted Meta Flow lifecycle)
"""

import hmac
import hashlib
import json
import logging
from decimal import Decimal
from typing import Any, Dict

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from orders.models import Category, Product, FlowSession, Order
from .flow_crypto import decrypt_flow_request, encrypt_flow_response, FlowCryptoError
from .services import send_flow_trigger_message, normalize_phone_number
from .tasks import send_confirmation_task

logger = logging.getLogger(__name__)

# Standard Quantity options
QUANTITY_OPTIONS = [
    {"id": "qty_1", "title": "1 kg (or bunch)", "multiplier": 1},
    {"id": "qty_2", "title": "2 kg", "multiplier": 2},
    {"id": "qty_3", "title": "3 kg", "multiplier": 3},
    {"id": "qty_5", "title": "5 kg (Family Pack)", "multiplier": 5},
]
QUANTITY_MAP = {q["id"]: q for q in QUANTITY_OPTIONS}
DEFAULT_DELIVERY_FEE = Decimal("5.00")


class MessagesWebhookView(APIView):
    """
    Webhook receiver for WhatsApp Cloud API incoming messages and Meta handshake.
    """
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        """
        Meta Webhook verification handshake:
        Validates hub.verify_token and returns hub.challenge plain text.
        """
        mode = request.query_params.get("hub.mode")
        token = request.query_params.get("hub.verify_token")
        challenge = request.query_params.get("hub.challenge")

        verify_token = getattr(settings, "WHATSAPP_VERIFY_TOKEN", "")
        if mode == "subscribe" and token == verify_token:
            logger.info("[Webhook] Verification successful.")
            return HttpResponse(challenge, content_type="text/plain", status=200)

        logger.warning("[Webhook] Verification failed (token mismatch).")
        return HttpResponse("Forbidden", content_type="text/plain", status=403)

    def post(self, request):
        """
        Processes incoming WhatsApp events.
        Verifies X-Hub-Signature-256 HMAC and triggers Flow on matching keywords.
        """
        raw_body = request.body

        # 1. Verify X-Hub-Signature-256 if WHATSAPP_APP_SECRET is configured
        app_secret = getattr(settings, "WHATSAPP_APP_SECRET", "")
        if app_secret:
            signature_header = request.headers.get("X-Hub-Signature-256", "")
            if not signature_header or not signature_header.startswith("sha256="):
                logger.warning("[Webhook] Missing or invalid signature header.")
                return Response({"error": "Missing signature"}, status=status.HTTP_403_FORBIDDEN)

            expected_sig = "sha256=" + hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected_sig, signature_header):
                logger.warning("[Webhook] Signature verification failed.")
                return Response({"error": "Invalid signature"}, status=status.HTTP_403_FORBIDDEN)

        # 2. Fast ACK: parse incoming message and dispatch async/promptly
        try:
            payload = json.loads(raw_body.decode("utf-8"))
            entry = payload.get("entry", [])
            for ent in entry:
                changes = ent.get("changes", [])
                for chg in changes:
                    value = chg.get("value", {})
                    messages = value.get("messages", [])
                    for msg in messages:
                        sender_num = msg.get("from")
                        msg_type = msg.get("type", "")

                        text_body = ""
                        if msg_type == "text":
                            text_body = msg.get("text", {}).get("body", "").strip()

                        lower_text = text_body.lower()
                        # Case-insensitive keyword trigger: "hi", "hello", "start", "order"
                        if any(kw in lower_text for kw in ["hi", "hello", "start", "order"]):
                            logger.info("[Webhook] Trigger keyword matched from +%s: '%s'", sender_num, text_body)
                            self._handle_flow_trigger(sender_num)

        except Exception as exc:
            logger.exception("[Webhook] Exception processing incoming payload: %s", exc)

        # Webhook must always ACK 200 fast
        return Response({"status": "received"}, status=status.HTTP_200_OK)

    def _handle_flow_trigger(self, phone: str):
        """
        Creates or resets FlowSession for the phone number and sends interactive Flow message.
        """
        normalized_phone = normalize_phone_number(phone)
        if not normalized_phone:
            return

        # Reset / create new FlowSession
        session, created = FlowSession.objects.update_or_create(
            customer_phone=normalized_phone,
            defaults={
                "current_screen": "PRODUCTS",
                "status": FlowSession.Status.DRAFT,
                "selected_category": None,
                "selected_product": None,
                "selected_quantity": "1 kg (or bunch)",
                "total_payable": Decimal("0.00"),
                "full_name": "",
                "phone_number": normalized_phone,
                "delivery_address": "",
            }
        )

        testing_mode = getattr(settings, "TESTING_MODE", False)
        if testing_mode:
            logger.info("Draft mode active — trigger flow manually via Preview in WhatsApp Manager")
            return

        flow_id = getattr(settings, "WHATSAPP_FLOW_ID", "1422173683118152")
        send_flow_trigger_message(
            to_phone=normalized_phone,
            flow_id=flow_id,
            flow_token=str(session.flow_token),
            flow_cta="Start Order"
        )


class FlowHealthCheckView(APIView):
    """
    Simple unencrypted health check endpoint for Meta Flow validator or developer connectivity checks.
    GET /webhook/flow-data-exchange/health/
    """
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        logger.info("[FlowHealthCheck] Health check ping received.")
        return Response(
            {
                "status": "ok",
                "service": "whatsapp_flow_data_exchange",
                "testing_mode": getattr(settings, "TESTING_MODE", False),
                "timestamp": timezone.now().isoformat(),
            },
            status=status.HTTP_200_OK
        )


class FlowDataExchangeView(APIView):
    """
    WhatsApp Flow 'data_exchange' encrypted endpoint.
    Handles PRODUCTS -> DELIVERY -> SUMMARY -> COMPLETE lifecycle.
    """
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        """
        Fallback GET handler returning health status if Meta validator or browser pings the base endpoint.
        """
        logger.info("[FlowDataExchange] GET health ping received.")
        return Response(
            {
                "status": "ok",
                "service": "whatsapp_flow_data_exchange",
                "message": "Endpoint is reachable. Send encrypted POST payloads for flow data exchange.",
                "testing_mode": getattr(settings, "TESTING_MODE", False),
            },
            status=status.HTTP_200_OK
        )

    def post(self, request):
        try:
            body = request.data
            if not isinstance(body, dict):
                body = json.loads(request.body.decode("utf-8"))

            is_encrypted = (
                "encrypted_flow_data" in body
                and "encrypted_aes_key" in body
                and "initial_vector" in body
            )

            if is_encrypted:
                decrypted, aes_key, iv = decrypt_flow_request(body)

                if getattr(settings, "DEBUG", False):
                    logger.info(
                        "\n==================== [FLOW INCOMING DECRYPTED PAYLOAD] ====================\n"
                        "Action: %s | Screen: %s | Trigger: %s | Flow Token: %s\n"
                        "Form Data:\n%s\n"
                        "Full Decrypted Payload:\n%s\n"
                        "===========================================================================",
                        decrypted.get("action"),
                        decrypted.get("screen"),
                        decrypted.get("data", {}).get("trigger"),
                        decrypted.get("flow_token"),
                        json.dumps(decrypted.get("data", {}), indent=2, default=str),
                        json.dumps(decrypted, indent=2, default=str),
                    )

                response_data = self.process_flow_lifecycle(decrypted)

                if getattr(settings, "DEBUG", False):
                    logger.info(
                        "\n==================== [FLOW OUTGOING RESPONSE (PRE-ENCRYPTION)] ============\n"
                        "Target Screen: %s\n"
                        "Response Payload:\n%s\n"
                        "===========================================================================",
                        response_data.get("screen", "N/A"),
                        json.dumps(response_data, indent=2, default=str),
                    )

                encrypted_resp = encrypt_flow_response(response_data, aes_key, iv)
                return HttpResponse(encrypted_resp, content_type="text/plain", status=200)
            else:
                # Plain JSON fallback for local testing & development
                if getattr(settings, "DEBUG", False):
                    logger.info(
                        "\n==================== [FLOW INCOMING PLAIN PAYLOAD (LOCAL DEV)] ============\n"
                        "Action: %s | Screen: %s | Trigger: %s | Flow Token: %s\n"
                        "Form Data:\n%s\n"
                        "Full Payload:\n%s\n"
                        "===========================================================================",
                        body.get("action"),
                        body.get("screen"),
                        body.get("data", {}).get("trigger"),
                        body.get("flow_token"),
                        json.dumps(body.get("data", {}), indent=2, default=str),
                        json.dumps(body, indent=2, default=str),
                    )

                response_data = self.process_flow_lifecycle(body)

                if getattr(settings, "DEBUG", False):
                    logger.info(
                        "\n==================== [FLOW OUTGOING RESPONSE (PLAIN DEV)] =================\n"
                        "Target Screen: %s\n"
                        "Response Payload:\n%s\n"
                        "===========================================================================",
                        response_data.get("screen", "N/A"),
                        json.dumps(response_data, indent=2, default=str),
                    )

                return Response(response_data, status=status.HTTP_200_OK)

        except FlowCryptoError as crypto_err:
            logger.error("[FlowDataExchange] Decryption error: %s", crypto_err)
            # Meta Flow specification requires HTTP 421 on cryptographic mismatch
            return HttpResponse("Flow Decryption Error", content_type="text/plain", status=421)

        except Exception as exc:
            logger.exception("[FlowDataExchange] General error: %s", exc)
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    def process_flow_lifecycle(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Routes the Flow state transitions per specification.
        """
        action = payload.get("action")
        screen = payload.get("screen", "")
        data = payload.get("data", {})
        flow_token = payload.get("flow_token", "")

        logger.info("[FlowDataExchange] action=%s screen=%s trigger=%s", action, screen, data.get("trigger"))

        # 1. Health check ping
        if action == "ping":
            return {"data": {"status": "active"}}

        # 2. Flow Opening (INIT)
        if action == "INIT":
            return {
                "screen": "PRODUCTS",
                "data": self._get_products_screen_data()
            }

        # 3. Data Exchange Screen Transitions
        if action == "data_exchange":
            trigger = data.get("trigger")

            # ── SCREEN 1: PRODUCTS ───────────────────────────────────────────
            if screen == "PRODUCTS":
                cat_id = data.get("category", "")
                prod_id = data.get("product", "")
                qty_id = data.get("quantity", "qty_1")

                # Check if navigating to DELIVERY
                is_continue = (
                    data.get("continue_to_delivery") is True
                    or trigger == "continue_to_delivery"
                    or "customer_name" in data
                )

                if not is_continue:
                    # trigger == 'category_selected' or 'product_selected'
                    return {
                        "screen": "PRODUCTS",
                        "data": self._get_products_screen_data(cat_id, prod_id, qty_id)
                    }

                # Navigate action to DELIVERY: save selections to FlowSession, compute total_payable
                return self._transition_to_delivery(flow_token, cat_id, prod_id, qty_id, data)

            # ── SCREEN 2: DELIVERY ───────────────────────────────────────────
            if screen == "DELIVERY":
                return self._transition_to_summary(flow_token, data)

            # ── SCREEN 3: SUMMARY ────────────────────────────────────────────
            if screen == "SUMMARY":
                action_type = data.get("action", "")
                # Final submit: create Order, mark status=complete, return COMPLETE
                return self._finalize_order(flow_token, data)

            # ── SCREEN 4: COMPLETE ───────────────────────────────────────────
            if screen == "COMPLETE":
                return {"data": {"status": "done"}}

        return {"data": {"error": f"Unhandled flow action '{action}' on screen '{screen}'"}}

    def _get_products_screen_data(self, cat_id: str = None, prod_id: str = None, qty_id: str = "qty_1") -> dict:
        """
        Builds the dynamic data payload for the PRODUCTS screen.
        """
        cat_order = ["cat_veg", "cat_fruits", "cat_greens"]
        categories = list(Category.objects.all().values("id", "name"))
        if not categories:
            categories = [
                {"id": "cat_veg", "name": "🥕 Fresh Vegetables"},
                {"id": "cat_fruits", "name": "🍎 Farm Fresh Fruits"},
                {"id": "cat_greens", "name": "🥬 Organic Greens"},
            ]

        # Order categories explicitly: Vegetables -> Fruits -> Greens
        cat_map = {c["id"]: c["name"] for c in categories}
        cat_choices = []
        for cid in cat_order:
            if cid in cat_map:
                cat_choices.append({"id": cid, "title": cat_map[cid]})
        for c in categories:
            if c["id"] not in cat_order:
                cat_choices.append({"id": c["id"], "title": c["name"]})

        if not cat_id or not any(c["id"] == cat_id for c in cat_choices):
            cat_id = "cat_veg" if any(c["id"] == "cat_veg" for c in cat_choices) else cat_choices[0]["id"]

        # Filter products per selected category with explicit ordering
        veg_order = ["prod_16", "prod_29", "prod_15", "prod_34", "prod_21", "prod_19"]
        prods_qs = Product.objects.filter(category_id=cat_id)
        if prods_qs.exists():
            items = [
                {"id": p.id, "title": p.dropdown_title, "unit_rate": float(p.unit_rate), "name": p.name}
                for p in prods_qs
            ]
            if cat_id == "cat_veg":
                item_map = {item["id"]: item for item in items}
                prod_choices = [item_map[pid] for pid in veg_order if pid in item_map]
                for item in items:
                    if item["id"] not in veg_order:
                        prod_choices.append(item)
            else:
                prod_choices = items
        else:
            prod_choices = [
                {"id": "prod_16", "title": "Ooty Red Carrot (₹80/kg)", "unit_rate": 80.0, "name": "Ooty Red Carrot"},
                {"id": "prod_29", "title": "Fresh Orange Carrot (₹75/kg)", "unit_rate": 75.0, "name": "Fresh Orange Carrot"},
                {"id": "prod_15", "title": "Regular Carrot (₹70/kg)", "unit_rate": 70.0, "name": "Regular Carrot"},
                {"id": "prod_34", "title": "Organic Tomatoes (₹40/kg)", "unit_rate": 40.0, "name": "Organic Tomatoes"},
                {"id": "prod_21", "title": "Farm Fresh Potato (₹40/kg)", "unit_rate": 40.0, "name": "Farm Fresh Potato"},
                {"id": "prod_19", "title": "Beetroot (₹45/kg)", "unit_rate": 45.0, "name": "Beetroot"},
            ]

        if not prod_id or not any(p["id"] == prod_id for p in prod_choices):
            prod_id = "prod_16" if any(p["id"] == "prod_16" for p in prod_choices) else prod_choices[0]["id"]

        selected_prod = next(p for p in prod_choices if p["id"] == prod_id)
        unit_rate = selected_prod["unit_rate"]

        qty_obj = QUANTITY_MAP.get(qty_id, QUANTITY_OPTIONS[0])
        multiplier = qty_obj["multiplier"]

        subtotal = unit_rate * multiplier
        delivery_fee = float(DEFAULT_DELIVERY_FEE)
        total_amount = subtotal + delivery_fee

        return {
            "categories": cat_choices,
            "products": [{"id": p["id"], "title": p["title"]} for p in prod_choices],
            "quantities": [{"id": q["id"], "title": q["title"]} for q in QUANTITY_OPTIONS],
            "selected_category": cat_id,
            "selected_product": prod_id,
            "selected_quantity": qty_id,
            "unit_rate": f"₹ {unit_rate:.2f}/kg",
            "unit_price": f"₹ {unit_rate:.2f}/kg",
            "subtotal": f"₹ {subtotal:.2f}",
            "delivery_fee": f"₹ {delivery_fee:.2f}",
            "total_amount": f"₹ {total_amount:.2f}",
        }

    def _transition_to_delivery(self, flow_token: str, cat_id: str, prod_id: str, qty_id: str, data: dict) -> dict:
        """
        Saves selections to FlowSession, computes total_payable, and returns DELIVERY screen.
        """
        screen_data = self._get_products_screen_data(cat_id, prod_id, qty_id)
        prod_obj = Product.objects.filter(id=prod_id).first()
        cat_obj = Category.objects.filter(id=cat_id).first()

        qty_item = QUANTITY_MAP.get(qty_id, QUANTITY_OPTIONS[0])
        unit_rate = Decimal(str(prod_obj.unit_rate)) if prod_obj else Decimal("80.00")
        total_payable = (unit_rate * qty_item["multiplier"]) + DEFAULT_DELIVERY_FEE

        # Update FlowSession
        session = None
        if flow_token:
            session = FlowSession.objects.filter(flow_token=flow_token).first()
        if not session and "customer_phone" in data:
            session = FlowSession.objects.filter(customer_phone=data["customer_phone"]).first()

        if session:
            session.selected_category = cat_obj
            session.selected_product = prod_obj
            session.selected_quantity = qty_item["title"]
            session.total_payable = total_payable
            session.current_screen = "DELIVERY"
            session.status = FlowSession.Status.DELIVERY
            session.save()

        prod_name = prod_obj.name if prod_obj else "Ooty Red Carrot"
        return {
            "screen": "DELIVERY",
            "data": {
                "product_id": prod_id,
                "product_name": prod_name,
                "quantity": qty_item["title"],
                "unit_price": f"₹ {unit_rate:.2f}/kg",
                "subtotal": screen_data["subtotal"],
                "delivery_fee": screen_data["delivery_fee"],
                "total_amount": f"₹ {total_payable:.2f}",
                "payment_mode": "COD",
            }
        }

    def _transition_to_summary(self, flow_token: str, data: dict) -> dict:
        """
        Validates full_name and phone_number, updates FlowSession, and returns SUMMARY screen recap.
        """
        full_name = str(data.get("customer_name", data.get("full_name", ""))).strip()
        phone_number = str(data.get("delivery_phone", data.get("phone_number", ""))).strip()
        address = str(data.get("delivery_address", data.get("address", ""))).strip()
        payment_mode = str(data.get("payment_mode", "COD")).upper()
        payment_label = "Cash on Delivery (COD)" if "COD" in payment_mode else "UPI on Delivery"

        # Update FlowSession
        session = None
        if flow_token:
            session = FlowSession.objects.filter(flow_token=flow_token).first()

        if session:
            session.full_name = full_name or session.full_name
            session.phone_number = phone_number or session.phone_number
            session.delivery_address = address
            session.current_screen = "SUMMARY"
            session.status = FlowSession.Status.SUMMARY
            session.save()

        prod_id = data.get("product_id", "")
        prod_obj = Product.objects.filter(id=prod_id).first()
        prod_name = prod_obj.name if prod_obj else data.get("product_name", "Ooty Red Carrot")

        return {
            "screen": "SUMMARY",
            "data": {
                "product_id": prod_id,
                "product_name": prod_name,
                "quantity": data.get("quantity", "1 kg (or bunch)"),
                "unit_price": data.get("unit_price", "₹ 80.00/kg"),
                "subtotal": data.get("subtotal", "₹ 80.00"),
                "delivery_fee": data.get("delivery_fee", "₹ 5.00"),
                "total_amount": data.get("total_amount", "₹ 85.00"),
                "customer_name": full_name or "Valued Customer",
                "delivery_address": address or "Farm Fresh Delivery Address",
                "delivery_phone": phone_number or "918807856058",
                "payment_mode": payment_label,
            }
        }

    def _finalize_order(self, flow_token: str, data: dict) -> dict:
        """
        Final submit: Creates Order from FlowSession, marks status=complete,
        triggers Celery confirmation task, and returns COMPLETE screen.
        """
        session = None
        if flow_token:
            session = FlowSession.objects.filter(flow_token=flow_token).first()

        # If session wasn't tracked by token, fallback to phone
        phone_num = str(data.get("delivery_phone", data.get("customer_phone", ""))).strip()
        if not session and phone_num:
            session = FlowSession.objects.filter(customer_phone=normalize_phone_number(phone_num)).first()

        prod_id = data.get("product_id", "")
        product = Product.objects.filter(id=prod_id).first()
        if not product and session and session.selected_product:
            product = session.selected_product
        if not product:
            product = Product.objects.first()

        quantity_str = data.get("quantity", "1 kg (or bunch)")
        unit_rate = product.unit_rate if product else Decimal("80.00")

        # Parse total payable
        total_raw = str(data.get("total_amount", "")).replace("₹", "").replace(",", "").strip()
        try:
            total_payable = Decimal(total_raw)
        except Exception:
            total_payable = Decimal("85.00")

        customer_name = str(data.get("customer_name", "")).strip() or (session.full_name if session else "Customer")
        delivery_address = str(data.get("delivery_address", "")).strip() or (session.delivery_address if session else "Delivery Address")
        customer_phone = normalize_phone_number(phone_num or (session.customer_phone if session else "918807856058"))

        # Create FlowSession if none existed
        if not session:
            session = FlowSession.objects.create(
                customer_phone=customer_phone,
                full_name=customer_name,
                phone_number=customer_phone,
                delivery_address=delivery_address,
                selected_product=product,
                selected_quantity=quantity_str,
                total_payable=total_payable,
                status=FlowSession.Status.COMPLETE,
                current_screen="COMPLETE"
            )
        else:
            session.status = FlowSession.Status.COMPLETE
            session.current_screen = "COMPLETE"
            session.save()

        # Idempotent Order Creation
        order, created = Order.objects.get_or_create(
            session=session,
            defaults={
                "product": product,
                "quantity": quantity_str,
                "unit_rate": unit_rate,
                "total_payable": total_payable,
                "customer_name": customer_name,
                "customer_phone": customer_phone,
                "delivery_address": delivery_address,
                "status": Order.Status.CONFIRMED,
            }
        )

        logger.info("[FlowDataExchange] Order #%s created/resolved for +%s", order.id, customer_phone)

        # Trigger Celery confirmation task
        try:
            send_confirmation_task.delay(order.id)
            logger.info("[FlowDataExchange] Enqueued Celery send_confirmation_task for Order #%s", order.id)
        except Exception as celery_err:
            logger.warning("[FlowDataExchange] Celery delay fallback (running direct): %s", celery_err)
            try:
                from .tasks import send_confirmation_task as direct_task
                direct_task(order.id)
            except Exception as direct_err:
                logger.error("[FlowDataExchange] Direct confirmation task error: %s", direct_err)

        return {
            "screen": "COMPLETE",
            "data": {
                "order_id": f"ORD-{order.id}",
                "message": (
                    f"Order ORD-{order.id} confirmed! Fresh produce is packed "
                    f"and our delivery rider will bring it to your doorstep."
                )
            }
        }
