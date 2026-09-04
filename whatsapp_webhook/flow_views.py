"""
whatsapp_webhook/flow_views.py
───────────────────────────────
Django view for the WhatsApp Flows endpoint.

Endpoint URL: POST /whatsapp/flow/
Register this URL in Meta App Dashboard → WhatsApp → Flows → fram_check → Edit → Endpoint URI.
"""

import json
import logging
import traceback

from django.http  import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .flow_handler import decrypt_flow_request, encrypt_flow_response, process_flow_action

logger = logging.getLogger(__name__)

import json
import logging
import traceback
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)


def process_flow_action(decrypted_body: dict) -> dict:
    """
    Routes an incoming Flow request to the right handler based on `action`.
    """
    action = decrypted_body.get("action")

    # ── Meta's "Verify endpoint" health check ──────────────────────────
    if action == "ping":
        return {
            "version": decrypted_body.get("version", "3.0"),
            "data": {"status": "active"},
        }

    # ── User closed/cancelled the flow ─────────────────────────────────
    if action == "INIT":
        # Return the data for the first screen
        return {
            "version": decrypted_body.get("version", "3.0"),
            "screen": "FIRST_SCREEN_ID",   # <-- your actual first screen name
            "data": {},
        }

    if action == "data_exchange":
        screen = decrypted_body.get("screen")
        data = decrypted_body.get("data", {})
        logger.info("[Flow] data_exchange on screen=%s data=%s", screen, data)

        # ── your real business logic per screen goes here ──────────────
        # example:
        # if screen == "FIRST_SCREEN_ID":
        #     return {
        #         "version": "3.0",
        #         "screen": "NEXT_SCREEN_ID",
        #         "data": {...},
        #     }

        return {
            "version": "3.0",
            "screen": screen,
            "data": data,
        }

    if action == "BACK":
        return {
            "version": decrypted_body.get("version", "3.0"),
            "screen": decrypted_body.get("screen"),
            "data": decrypted_body.get("data", {}),
        }

    # ── fallback ─────────────────────────────────────────────────────
    logger.warning("[Flow] Unknown action received: %s", action)
    return {
        "version": decrypted_body.get("version", "3.0"),
        "data": {"status": "active"},
    }


@csrf_exempt
def whatsapp_flow_endpoint(request):
    """
    Receives encrypted POST from Meta WhatsApp Flows, decrypts, processes,
    and returns an encrypted response.

    Also handles GET requests as a lightweight health check.
    """
    if request.method == "GET":
        return JsonResponse(
            {
                "status": "active",
                "endpoint": "/api/whatsapp/flow/",
                "service": "WhatsApp Flow Data Exchange",
            },
            status=200,
        )

    if request.method != "POST":
        return HttpResponse("Method Not Allowed", status=405)

    try:
        body_raw = request.body.decode("utf-8")
        body = json.loads(body_raw)

        logger.info("[Flow] Incoming request keys: %s", list(body.keys()))

        is_encrypted = (
            "encrypted_flow_data" in body
            and "encrypted_aes_key" in body
            and "initial_vector" in body
        )

        if is_encrypted:
            decrypted, aes_key, iv = decrypt_flow_request(body)
            logger.info("[Flow] Decrypted payload: %s", decrypted)

            response_data = process_flow_action(decrypted)
            encrypted_resp = encrypt_flow_response(response_data, aes_key, iv)

            return HttpResponse(
                encrypted_resp,
                content_type="text/plain",
                status=200,
            )
        else:
            logger.info("[Flow] Plain (unencrypted) request: %s", body)
            response_data = process_flow_action(body)
            return JsonResponse(response_data, status=200)

    except KeyError as exc:
        logger.error("[Flow] Missing field in request: %s", exc)
        return JsonResponse({"error": f"Missing field: {exc}"}, status=400)

    except Exception:
        logger.error("[Flow] Error processing flow request:\n%s", traceback.format_exc())
        return HttpResponse("Flow Processing Error", status=421)