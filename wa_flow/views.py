"""
wa_flow/views.py
────────────────
Thin HTTP view layer for WhatsApp Webhook and Flow Data-Exchange endpoints.
Delegates all business logic to services.py and cryptography to flow_crypto.py.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt

from .flow_crypto import FlowCryptoError, decrypt_flow_request, encrypt_flow_response
from .services import handle_flow_action, send_flow_message

logger = logging.getLogger(__name__)


@csrf_exempt
def webhook(request: HttpRequest) -> HttpResponse:
    """
    WhatsApp Cloud API Webhook endpoint:
    - GET: Hub verification handshake.
    - POST: Receives inbound events, triggers Flow on 'hi' or 'hello'.
    """
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        verify_token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")

        configured_token = getattr(settings, "VERIFY_TOKEN", "")

        if mode == "subscribe" and verify_token == configured_token:
            logger.info("[wa_flow] Webhook verification challenge accepted.")
            return HttpResponse(challenge, content_type="text/plain", status=200)

        logger.warning("[wa_flow] Webhook verification failed. Token mismatch.")
        return HttpResponse("Verification token mismatch", status=403)

    if request.method == "POST":
        try:
            body: Dict[str, Any] = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            # Always return 200 to WhatsApp to avoid retry spam
            return HttpResponse("Invalid JSON", status=200)

        # Parse message entries safely
        try:
            for entry in body.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    messages = value.get("messages", [])
                    for msg in messages:
                        if msg.get("type") == "text":
                            text_body = msg.get("text", {}).get("body", "").strip().lower()
                            from_phone = msg.get("from", "")

                            # Trigger Flow on 'hi' or 'hello'
                            if text_body in ("hi", "hello"):
                                logger.info(
                                    "[wa_flow] Customer +%s sent greeting '%s' -> Sending Flow trigger",
                                    from_phone,
                                    text_body
                                )
                                send_flow_message(from_phone)

        except Exception as exc:
            # Swallow any processing errors, log, and return 200 immediately
            logger.exception("[wa_flow] Error parsing webhook payload: %s", exc)

        return HttpResponse("EVENT_RECEIVED", status=200)

    return HttpResponse("Method not allowed", status=405)


@csrf_exempt
def flow_endpoint(request: HttpRequest) -> HttpResponse:
    """
    WhatsApp Flow Data-Exchange endpoint:
    - Receives encrypted flow request (RSA-OAEP + AES-128-GCM).
    - Dispatches screen transitions via handle_flow_action().
    - Returns encrypted response with bitwise-inverted IV (AES-128-GCM).
    - Returns HTTP 421 on any decryption or runtime failure per Meta specification.
    """
    if request.method != "POST":
        return HttpResponse("Method not allowed", status=405)

    try:
        try:
            payload: Dict[str, Any] = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as err:
            logger.error("[wa_flow] Non-JSON payload received at flow endpoint: %s", err)
            return HttpResponse("Malformed JSON", status=421)

        # 1. Decrypt request using RSA-OAEP + AES-128-GCM
        decrypted_data, aes_key, iv = decrypt_flow_request(payload)

        # 2. Dispatch business logic to obtain next screen state
        response_data = handle_flow_action(decrypted_data)

        # 3. Encrypt response using same AES key and inverted IV
        encrypted_response_b64 = encrypt_flow_response(response_data, aes_key, iv)

        return HttpResponse(encrypted_response_b64, content_type="text/plain", status=200)

    except FlowCryptoError as crypto_err:
        logger.warning("[wa_flow] Crypto error encountered: %s", crypto_err)
        # HTTP 421 informs WhatsApp to re-fetch business keys or retry exchange
        return HttpResponse("Decryption / Encryption Error", status=421)

    except Exception as exc:
        logger.exception("[wa_flow] Unhandled error in flow_endpoint: %s", exc)
        return HttpResponse("Internal Flow Processing Error", status=421)
