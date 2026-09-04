import json
import logging
import sys
from datetime import datetime

from decouple import config
from django.http import HttpResponse, JsonResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_GET

logger = logging.getLogger(__name__)

# Read from .env via python-decouple
VERIFY_TOKEN = config("WHATSAPP_VERIFY_TOKEN", default="")

# ANSI terminal colors (safe ASCII, no emoji)
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"
BG_GREEN  = "\033[42m\033[30m"
BG_YELLOW = "\033[43m\033[30m"
BG_CYAN   = "\033[46m\033[30m"


def _safe_print(text: str) -> None:
    """Print to stdout, replacing unencodable characters safely on Windows with immediate flush."""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        encoded = text.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8", errors="replace")
        print(encoded, flush=True)


def _banner(title: str, color: str = CYAN) -> None:
    line = "=" * 65
    _safe_print(f"\n{color}{BOLD}{line}{RESET}")
    _safe_print(f"{color}{BOLD}  {title}{RESET}")
    _safe_print(f"{color}{BOLD}{line}{RESET}")


def _log(label: str, value: str, color: str = GREEN) -> None:
    _safe_print(f"  {BOLD}{color}>> {label}:{RESET} {value}")


@csrf_exempt
@require_http_methods(["GET", "POST"])
def whatsapp_webhook(request):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _banner(f"[WEBHOOK HIT] HTTP {request.method} /webhook/whatsapp/ @ {now_str}", BG_CYAN)
    _log("Client IP", str(request.META.get("REMOTE_ADDR")), CYAN)
    _log("Method",    request.method, CYAN)

    if request.method == "GET":
        return handle_verification(request)
    return handle_incoming_event(request)


def handle_verification(request):
    """
    Meta calls this once when you click 'Verify and save' in the dashboard.
    It sends: hub.mode, hub.verify_token, hub.challenge as query params.
    We must echo back hub.challenge as plain text if the token matches.
    """
    mode      = request.GET.get("hub.mode")
    token     = request.GET.get("hub.verify_token")
    challenge = request.GET.get("hub.challenge")

    _log("hub.mode",         str(mode),      CYAN)
    _log("hub.verify_token", str(token),     CYAN)
    _log("hub.challenge",    str(challenge), CYAN)

    if mode == "subscribe" and token and token == VERIFY_TOKEN:
        _banner("[OK] WHATSAPP WEBHOOK VERIFIED BY META", GREEN)
        _safe_print(f"  {GREEN}Verification successful! Challenge echoed back.{RESET}\n")
        logger.info("WhatsApp webhook verified successfully.")
        return HttpResponse(challenge, content_type="text/plain", status=200)

    # If opened in a browser for direct testing
    if not mode and not token:
        _safe_print(f"  {YELLOW}Direct browser access test - Webhook is ACTIVE and ONLINE.{RESET}\n")
        return HttpResponse(
            "<h3>✅ Fresh Trace WhatsApp Webhook is ACTIVE and LISTENING!</h3>"
            "<p>Your server and ngrok tunnel are working properly.</p>",
            content_type="text/html",
            status=200
        )

    _banner("[ERR] WHATSAPP WEBHOOK VERIFICATION FAILED", RED)
    _safe_print(f"  {RED}Expected token='{VERIFY_TOKEN}', got='{token}'{RESET}\n")
    logger.warning("WhatsApp webhook verification failed. mode=%s token=%s", mode, token)
    return HttpResponseForbidden("Verification failed")


def handle_incoming_event(request):
    """
    Meta calls this for every incoming message / status update after
    verification succeeds and you've subscribed to fields like 'messages'.
    """
    raw_body = request.body.decode("utf-8", errors="replace")
    _safe_print(f"\n  {CYAN}>> RAW INCOMING BODY ({len(raw_body)} bytes):{RESET}")
    _safe_print(f"  {raw_body[:500]}{'...' if len(raw_body) > 500 else ''}\n")

    try:
        payload = json.loads(raw_body)
    except (ValueError, UnicodeDecodeError):
        _banner("[ERR] WHATSAPP WEBHOOK -- INVALID JSON", RED)
        logger.warning("Received invalid JSON payload on WhatsApp webhook.")
        return JsonResponse({"error": "invalid json"}, status=400)

    # ─── Process each entry in the payload ────────────────────────────────────
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value    = change.get("value", {})
                messages = value.get("messages", [])
                contacts = {
                    c.get("wa_id"): c.get("profile", {}).get("name", "Unknown")
                    for c in value.get("contacts", [])
                }

                # ── Incoming customer messages ─────────────────────────────
                for msg in messages:
                    sender_num  = msg.get("from", "")
                    sender_name = contacts.get(sender_num, "Customer")
                    msg_type    = msg.get("type", "unknown")
                    msg_id      = msg.get("id", "")
                    timestamp   = msg.get("timestamp", "")
                    ts_human    = ""
                    if timestamp:
                        try:
                            ts_human = datetime.utcfromtimestamp(int(timestamp)).strftime("%Y-%m-%d %H:%M:%S UTC")
                        except Exception:
                            ts_human = str(timestamp)

                    # Extract reply text & interactive selection
                    reply_text = ""
                    list_reply_id = ""
                    if msg_type == "text":
                        reply_text = msg.get("text", {}).get("body", "").strip()
                    elif msg_type == "interactive":
                        interactive = msg.get("interactive", {})
                        list_reply_id = (
                            interactive.get("list_reply", {}).get("id")
                            or interactive.get("button_reply", {}).get("id")
                            or ""
                        )
                        reply_text = (
                            interactive.get("button_reply", {}).get("title")
                            or interactive.get("list_reply", {}).get("title")
                            or str(interactive)
                        ).strip()
                    else:
                        reply_text = f"[{msg_type.title()} message]" if msg_type != "unknown" else "[non-text reply]"

                    # ── Terminal banner for every customer message (Atomic Block) ─────────
                    card_lines = [
                        f"\n{BG_GREEN}{BOLD}{'=' * 68}{RESET}",
                        f"{BG_GREEN}{BOLD}  💬 NEW INCOMING CUSTOMER WHATSAPP MESSAGE                         {RESET}",
                        f"{GREEN}{BOLD}{'-' * 68}{RESET}",
                        f"  {BOLD}{GREEN}Customer Name :{RESET} {sender_name}",
                        f"  {BOLD}{GREEN}Phone Number  :{RESET} +{sender_num}",
                        f"  {BOLD}{CYAN}Message Type  :{RESET} {msg_type.upper()}",
                        f"  {BOLD}{CYAN}Timestamp     :{RESET} {ts_human or 'N/A'}",
                        f"  {BOLD}{CYAN}Message ID    :{RESET} {msg_id}",
                        f"{GREEN}{BOLD}{'-' * 68}{RESET}",
                        f"  {BG_GREEN}{BOLD}  >>> CUSTOMER SAYS: \"{reply_text}\"  {RESET}" if reply_text else f"  {YELLOW}[No text content]{RESET}",
                        f"{BG_GREEN}{BOLD}{'=' * 68}{RESET}\n"
                    ]
                    _safe_print("\n".join(card_lines))

                    # Also append to a dedicated log file for easy viewing
                    try:
                        with open("incoming_whatsapp_messages.txt", "a", encoding="utf-8") as lf:
                            lf.write(f"[{ts_human or datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] From: {sender_name} (+{sender_num}) | Message: {reply_text}\n")
                    except Exception:
                        pass

                    # Disconnected from WhatsAppFollowUp table as requested
                    # if sender_num:
                    #     _update_followup(sender_num, sender_name, reply_text)

                    # ── Flow Dispatch & Message Routing ─────────────────────────
                    if sender_num:
                        try:
                            from .services import send_flow_message, send_text_reply

                            lower_text = reply_text.strip().lower()

                            # A. Location pin attachment from customer
                            if msg_type == "location" and "location" in msg:
                                loc_payload = msg.get("location", {})
                                loc_lat = loc_payload.get("latitude")
                                loc_lng = loc_payload.get("longitude")
                                from orders.models import Order
                                last_active_order = Order.objects.filter(
                                    delivery_phone__icontains=sender_num[-10:],
                                    status__in=[Order.Status.CONFIRMED, Order.Status.OUT_FOR_DELIVERY]
                                ).first()
                                if last_active_order and loc_lat and loc_lng:
                                    last_active_order.delivery_latitude = loc_lat
                                    last_active_order.delivery_longitude = loc_lng
                                    last_active_order.save(update_fields=['delivery_latitude', 'delivery_longitude'])
                                    _safe_print(f"\n{BG_GREEN}{BOLD}  📍 [FLOW BOT] Updated Live GPS for Order #{last_active_order.id}: ({loc_lat}, {loc_lng})  {RESET}\n")
                                    domain = config("SITE_URL", default=config("NGROK_URL", default="https://upon-washday-aerobics.ngrok-free.dev")).rstrip("/")
                                    send_text_reply(
                                        sender_num,
                                        f"📍 *Live Location Updated!*\n"
                                        f"Coordinates synced for Order #{last_active_order.id}.\n\n"
                                        f"🚚 Track live: {domain}/orders/track/order/{last_active_order.id}/"
                                    )
                                else:
                                    send_text_reply(sender_num, "📍 Received your location pin! Our delivery rider will navigate to this GPS location upon order dispatch.")

                            # B. Only trigger Flow automatically when customer says "hi" or "hello" (Section 5)
                            elif lower_text in ["hi", "hello", "hey", "start", "order", "flow"]:
                                flow_id = config("WHATSAPP_FLOW_ID", default="2150521762194545")
                                _safe_print(f"\n{BG_CYAN}{BOLD}  🌾 [FLOW BOT] Customer +{sender_num} sent '{reply_text}' -> Dispatching WhatsApp Flow #{flow_id}  {RESET}\n")
                                flow_res = send_flow_message(
                                    to_phone=sender_num,
                                    cta_text="Order Produce",
                                    flow_id=flow_id
                                )
                                if flow_res.get("success"):
                                    _safe_print(f"  {GREEN}[FLOW BOT] WhatsApp Flow successfully sent via API to +{sender_num}{RESET}\n")
                                else:
                                    err_data = flow_res.get("error", {})
                                    _safe_print(f"  {RED}[FLOW BOT] WhatsApp Flow API dispatch error: {err_data}. STRICT NO WEB LINKS MODE.{RESET}\n")
                                    # Send clean text reply without any web links
                                    send_text_reply(
                                        sender_num,
                                        "🌿 *Fresh Trace Farm Market*\n\n"
                                        "Welcome! Our WhatsApp Ordering Flow is ready.\n"
                                        "Select your items to place an order directly on WhatsApp."
                                    )



                            # C. Polite replies for other message types (Do not spam Flow)
                            elif any(w in lower_text for w in ["thank", "thanks", "thx", "ok", "okay"]):
                                send_text_reply(
                                    sender_num,
                                    "🌿 You're welcome! Send *hi* whenever you would like to order fresh produce."
                                )
                            elif any(w in lower_text for w in ["where", "track", "status"]):
                                from orders.models import Order
                                last_order = Order.objects.filter(
                                    delivery_phone__icontains=sender_num[-10:]
                                ).order_by('-id').first()
                                if last_order:
                                    domain = config("SITE_URL", default=config("NGROK_URL", default="https://upon-washday-aerobics.ngrok-free.dev")).rstrip("/")
                                    send_text_reply(
                                        sender_num,
                                        f"📦 *Order #{last_order.id} Status: {last_order.get_status_display().upper()}*\n\n"
                                        f"💰 Total: ₹{last_order.total_amount:.2f}\n"
                                        f"🚚 Live Map: {domain}/orders/track/order/{last_order.id}/"
                                    )
                                else:
                                    send_text_reply(sender_num, "No recent orders found for this number. Send *hi* to start shopping!")
                            elif "help" in lower_text:
                                send_text_reply(
                                    sender_num,
                                    "🌾 *Fresh Trace Support*\n"
                                    "• Send *hi* to open our WhatsApp Ordering Flow\n"
                                    "• Send *track* to check your latest delivery status"
                                )
                            else:
                                send_text_reply(
                                    sender_num,
                                    "🌾 Welcome to Fresh Trace Farm Market! Send *hi* to open our fresh produce ordering flow."
                                )
                        except Exception as bot_err:
                            _safe_print(f"  {RED}[FLOW BOT] Error: {bot_err}{RESET}\n")

                # ── Delivery / read status updates ─────────────────────────
                statuses = value.get("statuses", [])
                for status in statuses:
                    s_status  = status.get("status", "").upper()
                    recipient = status.get("recipient_id", "")
                    color = GREEN if s_status == "READ" else CYAN if s_status == "DELIVERED" else YELLOW
                    _safe_print(f"\n  {color}{BOLD}[STATUS] Message to +{recipient} --> [{s_status}]{RESET}")

    except Exception as exc:
        _banner("[WARN] WEBHOOK PARSE WARNING", YELLOW)
        _safe_print(f"  {YELLOW}Error: {exc}{RESET}\n")
        logger.exception("Error parsing WhatsApp webhook payload: %s", exc)

    # Raw payload
    _safe_print(f"\n  {CYAN}-- Raw payload --------------------------------------------------{RESET}")
    _safe_print(f"  {json.dumps(payload, separators=(',', ':'))}")
    _safe_print(f"  {CYAN}-----------------------------------------------------------------{RESET}\n")

    logger.info("WhatsApp webhook payload: %s", json.dumps(payload))
    return JsonResponse({"status": "received"}, status=200)


def _update_followup(sender_num: str, sender_name: str, reply_text: str) -> None:
    """
    Find the matching WhatsAppFollowUp rows by phone number and mark them replied.
    Tries multiple phone number formats and falls back to a partial contains search.
    """
    try:
        from django.utils import timezone
        from .models import WhatsAppFollowUp

        raw_from = str(sender_num).strip().lstrip("+")

        # Build a rich list of candidate phone number formats
        phone_candidates = [raw_from, f"+{raw_from}"]
        if len(raw_from) >= 10:
            last10 = raw_from[-10:]
            phone_candidates.extend([
                last10, f"+{last10}",
                f"91{last10}", f"+91{last10}",
            ])
        phone_candidates = list(dict.fromkeys(phone_candidates))

        # 1st attempt: exact match on pending (unreplied) rows
        pending_qs = WhatsAppFollowUp.objects.filter(
            phone_number__in=phone_candidates,
            customer_replied=False,
        )
        match_count = pending_qs.count()

        _log("Phone lookup",              f"candidates={phone_candidates}", CYAN)
        _log("Pending rows (exact match)", str(match_count), GREEN if match_count else YELLOW)

        # 2nd attempt: partial contains match
        if match_count == 0:
            last10 = raw_from[-10:] if len(raw_from) >= 10 else raw_from
            pending_qs = WhatsAppFollowUp.objects.filter(
                phone_number__icontains=last10,
                customer_replied=False,
            )
            match_count = pending_qs.count()
            _log("Pending rows (contains)", str(match_count), GREEN if match_count else YELLOW)

        now = timezone.now()

        if match_count > 0:
            updated = pending_qs.update(
                customer_replied=True,
                customer_replied_at=now,
                last_reply_text=reply_text or "[non-text reply]",
            )
            _log("[OK] Dashboard updated", f"{updated} row(s) marked REPLIED", GREEN)
            _safe_print(f"  {BG_GREEN}{BOLD}  REPLY SAVED --> \"{reply_text}\"  {RESET}\n")
            logger.info(
                "[WhatsApp] Marked %d rows replied for +%s | text: %s",
                updated, sender_num, reply_text,
            )

        else:
            # Fallback: update the most recent row for this number
            last10 = raw_from[-10:] if len(raw_from) >= 10 else raw_from
            latest_row = WhatsAppFollowUp.objects.filter(
                phone_number__icontains=last10
            ).order_by("-interactive_message_sent_at").first()

            if latest_row:
                latest_row.customer_replied    = True
                latest_row.customer_replied_at = now
                latest_row.last_reply_text      = reply_text or "[non-text reply]"
                latest_row.save(update_fields=["customer_replied", "customer_replied_at", "last_reply_text"])
                _log("[OK] Dashboard updated (fallback)", f"row #{latest_row.id} updated", GREEN)
                _safe_print(f"  {BG_GREEN}{BOLD}  REPLY SAVED --> \"{reply_text}\"  {RESET}\n")
            else:
                # Create a brand-new tracking row for this inbound message
                new_row = WhatsAppFollowUp.objects.create(
                    customer_name=sender_name if sender_name != "Customer" else f"+{raw_from}",
                    phone_number=f"+{raw_from}",
                    interactive_message_sent_at=now,
                    customer_replied=True,
                    customer_replied_at=now,
                    last_reply_text=reply_text or "[non-text reply]",
                )
                _log("[OK] Dashboard updated (new row)", f"row #{new_row.id} created", GREEN)
                _safe_print(f"  {BG_GREEN}{BOLD}  REPLY SAVED --> \"{reply_text}\"  {RESET}\n")

    except Exception as err:
        _log("[ERR] DB update error", str(err), RED)
        logger.error("[WhatsApp] Error updating WhatsAppFollowUp: %s", err)


# ─── AJAX endpoint: latest replies for dashboard polling ──────────────────────
@require_GET
def latest_replies_api(request):
    """
    Returns the latest WhatsAppFollowUp rows that have a customer reply.
    Dashboard JS polls this every 20s to auto-refresh without full page reload.
    """
    from .models import WhatsAppFollowUp

    limit = int(request.GET.get("limit", 50))
    rows  = WhatsAppFollowUp.objects.filter(
        customer_replied=True
    ).order_by("-customer_replied_at")[:limit]

    data = []
    for row in rows:
        data.append({
            "id":                  row.id,
            "customer_name":       row.customer_name,
            "phone_number":        row.phone_number,
            "customer_replied":    row.customer_replied,
            "customer_replied_at": row.customer_replied_at.strftime("%b %d, %Y %I:%M %p") if row.customer_replied_at else None,
            "last_reply_text":     row.last_reply_text or "",
            "status_code":         row.status_code,
        })

    return JsonResponse({"replies": data, "count": len(data)})


# ─── TEST endpoint: simulate an incoming WhatsApp message ─────────────────────
@csrf_exempt
def simulate_whatsapp_message(request):
    """
    DEV ONLY -- simulates an incoming WhatsApp message from a customer.
    POST with: phone=918807856058&message=Hello+I+got+my+order
    This lets you test the full webhook->DB->dashboard pipeline without Meta/ngrok.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    phone   = request.POST.get("phone", "").strip()
    message = request.POST.get("message", "Test reply from customer").strip()
    name    = request.POST.get("name", "Test Customer").strip()

    if not phone:
        return JsonResponse({"error": "phone is required"}, status=400)

    _banner("[TEST] SIMULATED WHATSAPP MESSAGE (DEV TEST)", BG_YELLOW)
    _log("Phone",   phone,   YELLOW)
    _log("Message", message, YELLOW)

    _update_followup(phone, name, message)

    return JsonResponse({
        "success": True,
        "message": f"Simulated message from +{phone}: \"{message}\"",
        "phone":   phone,
    })


# ─── DEBUG endpoint: show webhook status & DB stats ──────────────────────────
@require_GET
def webhook_debug_status(request):
    """
    Returns a diagnostic JSON with DB stats and webhook config.
    """
    from .models import WhatsAppFollowUp
    from decouple import config as env

    total     = WhatsAppFollowUp.objects.count()
    replied   = WhatsAppFollowUp.objects.filter(customer_replied=True).count()
    pending   = WhatsAppFollowUp.objects.filter(customer_replied=False).count()
    phone_ids = list(WhatsAppFollowUp.objects.values_list("phone_number", flat=True).distinct()[:10])

    return JsonResponse({
        "webhook_url_paths": ["/webhook/whatsapp/", "/whatsapp/webhook/"],
        "verify_token_set":  bool(env("WHATSAPP_VERIFY_TOKEN", default="")),
        "phone_number_id":   env("WHATSAPP_PHONE_NUMBER_ID", default="NOT SET"),
        "access_token_set":  bool(env("WHATSAPP_ACCESS_TOKEN", default="")),
        "db_stats": {
            "total_followups": total,
            "replied":         replied,
            "pending":         pending,
        },
        "phone_numbers_in_db": phone_ids,
        "status": "OK",
    })


# ─── STEP 2: POST /api/whatsapp/create-flow/ ─────────────────────────────────
@csrf_exempt
@require_http_methods(["POST", "GET"])
def api_create_flow(request):
    """
    STEP 2: POST /api/whatsapp/create-flow/
    Dispatches to Meta (STEP 3: POST /{WABA_ID}/flows)
    Creates Flow as DRAFT (STEP 4) and registers endpoint_uri.
    """
    import requests
    from decouple import config as env

    token = env("WHATSAPP_ACCESS_TOKEN", default=env("WHATSAPP_TOKEN", default=""))
    waba_id = env("WHATSAPP_WABA_ID", default=env("WABA_ID", default=""))
    api_version = env("WHATSAPP_API_VERSION", default="v21.0")

    if not token or not waba_id:
        return JsonResponse({"error": "WHATSAPP_ACCESS_TOKEN and WHATSAPP_WABA_ID must be configured"}, status=400)

    flow_name = "fresh_trace_market_flow"
    want_publish = False
    if request.method == "POST":
        try:
            body = json.loads(request.body.decode("utf-8")) if request.body else {}
            flow_name = body.get("name", flow_name)
            want_publish = bool(body.get("publish", False))
        except Exception:
            flow_name = request.POST.get("name", flow_name)
            want_publish = request.POST.get("publish", "").lower() in ("true", "1")

    flow_path = "wa_flow/flow_definitions/flow.json"
    try:
        with open(flow_path, "r", encoding="utf-8") as f:
            flow_definition = json.load(f)
            flow_json_str = json.dumps(flow_definition)
    except Exception as read_err:
        return JsonResponse({"error": f"Failed to read/validate {flow_path}: {read_err}"}, status=500)

    url = f"https://graph.facebook.com/{api_version}/{waba_id}/flows"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "name": flow_name,
        "categories": ["OTHER"],
        "flow_json": flow_json_str
    }

    try:
        meta_res = requests.post(url, headers=headers, json=payload, timeout=20)
        res_data = meta_res.json()
        if meta_res.status_code in (200, 201):
            new_flow_id = res_data.get("id")
            domain = env("SITE_URL", default=env("NGROK_URL", default="")).rstrip("/")
            endpoint_url = f"{domain}/api/whatsapp/flow/"

            endpoint_reg_res = None
            endpoint_registered = False
            endpoint_error = None
            try:
                reg_resp = requests.post(
                    f"https://graph.facebook.com/{api_version}/{new_flow_id}",
                    headers=headers,
                    json={"endpoint_uri": endpoint_url},
                    timeout=15,
                )
                endpoint_reg_res = reg_resp.json()
                endpoint_registered = reg_resp.status_code in (200, 201) and endpoint_reg_res.get("success", True)
                if not endpoint_registered:
                    endpoint_error = endpoint_reg_res
            except Exception as ep_err:
                endpoint_error = str(ep_err)
                logger.error("[Flow Create] Failed to register endpoint URI: %s", ep_err)

            # Check if user requested auto-publishing
            publish_attempted = False
            publish_status_code = None
            publish_response = None
            flow_status = "DRAFT"

            if want_publish:
                publish_attempted = True
                try:
                    pub_res = requests.post(
                        f"https://graph.facebook.com/{api_version}/{new_flow_id}/publish",
                        headers=headers,
                        timeout=15
                    )
                    publish_status_code = pub_res.status_code
                    publish_response = pub_res.json()
                    if pub_res.status_code in (200, 201) and publish_response.get("success", True):
                        flow_status = "PUBLISHED"
                except Exception as pub_err:
                    publish_response = {"error": str(pub_err)}

            return JsonResponse({
                "success": True,
                "flow_id": new_flow_id,
                "name": flow_name,
                "status": flow_status,
                "mode": "draft" if flow_status == "DRAFT" else "published",
                "endpoint_registered": endpoint_registered,
                "endpoint_uri": endpoint_url,
                "publish_attempted": publish_attempted,
                "publish_status_code": publish_status_code,
                "publish_response": publish_response,
                "validation_errors": res_data.get("validation_errors", []),
                "meta_response": res_data
            }, status=201)
        else:
            # If flow already exists with this name, retrieve it and sync endpoint
            err_subcode = res_data.get("error", {}).get("error_subcode")
            if err_subcode == 4016019:
                try:
                    list_res = requests.get(f"https://graph.facebook.com/{api_version}/{waba_id}/flows", headers=headers, timeout=15)
                    if list_res.status_code == 200:
                        flows = list_res.json().get("data", [])
                        match = next((f for f in flows if f.get("name") == flow_name), None)
                        if match:
                            existing_id = match.get("id")
                            domain = env("SITE_URL", default=env("NGROK_URL", default="")).rstrip("/")
                            endpoint_url = f"{domain}/api/whatsapp/flow/"

                            # Sync endpoint URI
                            ep_res = requests.post(
                                f"https://graph.facebook.com/{api_version}/{existing_id}",
                                headers=headers,
                                json={"endpoint_uri": endpoint_url},
                                timeout=15
                            )
                            ep_data = ep_res.json()
                            ep_ok = ep_res.status_code in (200, 201) and ep_data.get("success", True)

                            pub_attempted = False
                            pub_code = None
                            pub_resp = None
                            curr_status = match.get("status", "DRAFT")

                            if want_publish:
                                pub_attempted = True
                                p_res = requests.post(
                                    f"https://graph.facebook.com/{api_version}/{existing_id}/publish",
                                    headers=headers,
                                    timeout=15
                                )
                                pub_code = p_res.status_code
                                pub_resp = p_res.json()
                                if pub_code in (200, 201) and pub_resp.get("success", True):
                                    curr_status = "PUBLISHED"

                            return JsonResponse({
                                "success": True,
                                "flow_id": existing_id,
                                "name": flow_name,
                                "status": curr_status,
                                "mode": "draft" if curr_status == "DRAFT" else "published",
                                "endpoint_registered": ep_ok,
                                "endpoint_uri": endpoint_url,
                                "publish_attempted": pub_attempted,
                                "publish_status_code": pub_code,
                                "publish_response": pub_resp,
                                "validation_errors": match.get("validation_errors", []),
                                "note": "Flow already existed; retrieved existing flow and synchronized endpoint"
                            }, status=200)
                except Exception as sync_err:
                    logger.warning("[Flow Create] Failed to sync existing flow: %s", sync_err)

            return JsonResponse({
                "success": False,
                "status_code": meta_res.status_code,
                "error": res_data
            }, status=meta_res.status_code)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)


# ─── STEP 6: POST /api/whatsapp/publish-flow/ ────────────────────────────────
@csrf_exempt
@require_http_methods(["POST"])
def api_publish_flow(request):
    """
    STEP 6: POST /api/whatsapp/publish-flow/
    Calls Meta: POST /{FLOW_ID}/publish
    Only publishes when intentionally requested.
    """
    import requests
    from decouple import config as env

    token = env("WHATSAPP_ACCESS_TOKEN", default=env("WHATSAPP_TOKEN", default=""))
    api_version = env("WHATSAPP_API_VERSION", default="v21.0")
    flow_id = env("WHATSAPP_FLOW_ID", default=env("FLOW_ID", default=""))

    try:
        if request.body:
            body = json.loads(request.body.decode("utf-8"))
            flow_id = body.get("flow_id", flow_id)
    except Exception:
        flow_id = request.POST.get("flow_id", flow_id)

    if not token or not flow_id:
        return JsonResponse({"error": "WHATSAPP_ACCESS_TOKEN and flow_id are required to publish."}, status=400)

    url = f"https://graph.facebook.com/{api_version}/{flow_id}/publish"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        meta_res = requests.post(url, headers=headers, timeout=15)
        res_data = meta_res.json()
        return JsonResponse({
            "step": "STEP 6: Publish Flow",
            "flow_id": flow_id,
            "status_code": meta_res.status_code,
            "response": res_data
        }, status=meta_res.status_code if meta_res.status_code in (200, 201) else 400)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)


# ─── STEP 7: POST /api/whatsapp/send-flow/ ───────────────────────────────────
@csrf_exempt
@require_http_methods(["POST"])
def api_send_flow(request):
    """
    STEP 7: POST /api/whatsapp/send-flow/
    Uses Flow ID to dispatch Flow message to recipient phone number.
    Payload: {"to_phone": "918807856058", "flow_id": "1422173683118152"}
    """
    from .services import send_flow_message
    from decouple import config as env

    phone = None
    flow_id = None

    try:
        if request.body:
            body = json.loads(request.body.decode("utf-8"))
            phone = body.get("to_phone", body.get("phone"))
            flow_id = body.get("flow_id")
    except Exception:
        phone = request.POST.get("to_phone", request.POST.get("phone"))
        flow_id = request.POST.get("flow_id")

    if not phone:
        phone = env("WHATSAPP_TEST_RECIPIENT_PHONE", default="918807856058")

    res = send_flow_message(to_phone=phone, flow_id=flow_id)
    return JsonResponse({
        "step": "STEP 7: Use Flow ID to send Flow",
        "to_phone": phone,
        "result": res
    }, status=200 if res.get("success") else 400)

