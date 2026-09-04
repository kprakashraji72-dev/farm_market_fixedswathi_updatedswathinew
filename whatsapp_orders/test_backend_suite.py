"""
test_backend_suite.py
─────────────────────
End-to-End Automated Test Suite validating all requirements of the
WhatsApp Flow-based ordering backend:
1. GET /webhook/messages/ (Meta verification challenge)
2. POST /webhook/messages/ (Trigger keyword "hi" -> FlowSession reset & Fast ACK)
3. POST /webhook/flow-data-exchange/ (action=ping)
4. POST /webhook/flow-data-exchange/ (action=INIT -> screen=PRODUCTS)
5. POST /webhook/flow-data-exchange/ (trigger=category_selected -> filtered products)
6. POST /webhook/flow-data-exchange/ (trigger=product_selected -> unit_rate calculation)
7. POST /webhook/flow-data-exchange/ (navigate to DELIVERY -> FlowSession update & total_payable)
8. POST /webhook/flow-data-exchange/ (navigate to SUMMARY -> name/phone validation & recap)
9. POST /webhook/flow-data-exchange/ (action=complete -> Order created & status=complete)
10. Flow Crypto: RSA-OAEP + AES-GCM Encrypted payload round-trip
11. Celery cleanup_stale_sessions_task test
"""

import os
import sys

base_dir = os.path.dirname(os.path.abspath(__file__))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

import json
import django
from decimal import Decimal

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "whatsapp_orders.settings")
django.setup()

from django.test import RequestFactory
from django.conf import settings
from orders.models import Category, Product, FlowSession, Order
from whatsapp.views import MessagesWebhookView, FlowDataExchangeView, FlowHealthCheckView
from whatsapp.flow_crypto import decrypt_flow_request, encrypt_flow_response, _load_rsa_private_key
from whatsapp.tasks import cleanup_stale_sessions_task

rf = RequestFactory()
passed = 0
failed = 0

def check(test_num: int, name: str, condition: bool, details: str = ""):
    global passed, failed
    status_str = "PASS" if condition else "FAIL"
    symbol = "[OK]" if condition else "[X]"
    print(f"{symbol} [TEST {test_num}: {status_str}] {name}")
    if details:
        safe_details = details.encode("ascii", "replace").decode("ascii")
        print(f"    -> {safe_details}")
    if condition:
        passed += 1
    else:
        failed += 1

print("\n" + "=" * 70)
print("  WHATSAPP FLOW ORDERING BACKEND COMPREHENSIVE VERIFICATION SUITE")
print("=" * 70 + "\n")

# ── TEST 1: GET /webhook/messages/ Handshake ─────────────────────────────────
try:
    view = MessagesWebhookView.as_view()
    verify_token = getattr(settings, "WHATSAPP_VERIFY_TOKEN", "fresh_trace_wa_c5a23fd481477ef350e8944373ddfe3a")

    req_valid = rf.get("/webhook/messages/", {
        "hub.mode": "subscribe",
        "hub.verify_token": verify_token,
        "hub.challenge": "meta_handshake_challenge_123"
    })
    resp_valid = view(req_valid)
    is_valid_ok = (resp_valid.status_code == 200 and resp_valid.content.decode() == "meta_handshake_challenge_123")

    req_bad = rf.get("/webhook/messages/", {
        "hub.mode": "subscribe",
        "hub.verify_token": "invalid_token",
        "hub.challenge": "bad_challenge"
    })
    resp_bad = view(req_bad)
    is_bad_rejected = (resp_bad.status_code == 403)

    check(1, "Meta Handshake Verification (GET /webhook/messages/)", is_valid_ok and is_bad_rejected,
          "Valid token returns 200 with challenge; invalid token returns 403")
except Exception as e:
    check(1, "Meta Handshake Verification", False, str(e))


# ── TEST 2: POST /webhook/messages/ Keyword Trigger & FlowSession Reset ───────
try:
    test_phone = "918807856058"
    webhook_body = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "1965689270778996",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "messages": [{
                        "from": test_phone,
                        "id": "wamid.test_001",
                        "timestamp": "1788500000",
                        "text": {"body": "Hi there, want to order"},
                        "type": "text"
                    }]
                },
                "field": "messages"
            }]
        }]
    }

    req_msg = rf.post("/webhook/messages/", data=json.dumps(webhook_body), content_type="application/json")
    resp_msg = view(req_msg)

    session = FlowSession.objects.filter(customer_phone=test_phone).first()
    t2_ok = (
        resp_msg.status_code == 200
        and session is not None
        and session.status == FlowSession.Status.DRAFT
        and session.current_screen == "PRODUCTS"
    )
    check(2, "Webhook Trigger Keyword & FlowSession Creation", t2_ok,
          f"HTTP 200 fast ACK, Session {session.flow_token} initialized for +{test_phone}")
except Exception as e:
    check(2, "Webhook Trigger Keyword", False, str(e))


# ── TEST 3: POST /webhook/flow-data-exchange/ Ping ───────────────────────────
try:
    flow_view = FlowDataExchangeView.as_view()
    req_ping = rf.post("/webhook/flow-data-exchange/", data=json.dumps({"action": "ping"}), content_type="application/json")
    resp_ping = flow_view(req_ping)
    data_ping = resp_ping.data
    check(3, "Flow Endpoint Healthcheck (action=ping)", data_ping.get("data", {}).get("status") == "active",
          f"Status: {data_ping.get('data', {}).get('status')}")
except Exception as e:
    check(3, "Flow Endpoint Healthcheck", False, str(e))


# ── TEST 4: POST /webhook/flow-data-exchange/ action=INIT ─────────────────────
try:
    req_init = rf.post("/webhook/flow-data-exchange/", data=json.dumps({"action": "INIT"}), content_type="application/json")
    resp_init = flow_view(req_init)
    data_init = resp_init.data
    t4_ok = (
        data_init.get("screen") == "PRODUCTS"
        and len(data_init.get("data", {}).get("categories", [])) >= 3
        and len(data_init.get("data", {}).get("products", [])) >= 1
    )
    check(4, "Flow Endpoint action=INIT -> PRODUCTS Screen", t4_ok,
          f"Categories count: {len(data_init.get('data', {}).get('categories', []))}, Products count: {len(data_init.get('data', {}).get('products', []))}")
except Exception as e:
    check(4, "Flow Endpoint action=INIT", False, str(e))


# ── TEST 5: trigger=category_selected -> Filtered Products ───────────────────
try:
    req_cat = rf.post("/webhook/flow-data-exchange/", data=json.dumps({
        "action": "data_exchange",
        "screen": "PRODUCTS",
        "data": {
            "trigger": "category_selected",
            "category": "cat_fruits",
            "product": "",
            "quantity": "qty_1"
        }
    }), content_type="application/json")
    resp_cat = flow_view(req_cat)
    data_cat = resp_cat.data
    prods_cat = data_cat.get("data", {}).get("products", [])
    t5_ok = (
        data_cat.get("screen") == "PRODUCTS"
        and any("Apple" in p["title"] or "Banana" in p["title"] for p in prods_cat)
    )
    check(5, "Category Selection Filter (trigger=category_selected)", t5_ok,
          f"Selected 'cat_fruits' returned items: {[p['title'] for p in prods_cat]}")
except Exception as e:
    check(5, "Category Selection Filter", False, str(e))


# ── TEST 6: trigger=product_selected -> Unit Rate Calculation ─────────────────
try:
    req_prod = rf.post("/webhook/flow-data-exchange/", data=json.dumps({
        "action": "data_exchange",
        "screen": "PRODUCTS",
        "data": {
            "trigger": "product_selected",
            "category": "cat_veg",
            "product": "prod_16",  # Ooty Red Carrot (80/kg)
            "quantity": "qty_2"     # 2 kg
        }
    }), content_type="application/json")
    resp_prod = flow_view(req_prod)
    data_prod = resp_prod.data
    t6_ok = (
        data_prod.get("screen") == "PRODUCTS"
        and "80.00" in data_prod.get("data", {}).get("unit_rate", "")
        and "160.00" in data_prod.get("data", {}).get("subtotal", "")
        and "165.00" in data_prod.get("data", {}).get("total_amount", "")
    )
    check(6, "Product & Quantity Rate Update (trigger=product_selected)", t6_ok,
          f"Unit rate: {data_prod.get('data', {}).get('unit_rate')}, Subtotal: {data_prod.get('data', {}).get('subtotal')}, Total: {data_prod.get('data', {}).get('total_amount')}")
except Exception as e:
    check(6, "Product Rate Update", False, str(e))


# ── TEST 7: Navigate to DELIVERY -> FlowSession Update ───────────────────────
try:
    req_deliv = rf.post("/webhook/flow-data-exchange/", data=json.dumps({
        "action": "data_exchange",
        "screen": "PRODUCTS",
        "flow_token": str(session.flow_token),
        "data": {
            "continue_to_delivery": True,
            "category": "cat_veg",
            "product": "prod_16",
            "quantity": "qty_3"  # 3 kg -> 80 * 3 = 240 + 5 = 245
        }
    }), content_type="application/json")
    resp_deliv = flow_view(req_deliv)
    data_deliv = resp_deliv.data

    session.refresh_from_db()
    t7_ok = (
        data_deliv.get("screen") == "DELIVERY"
        and session.status == FlowSession.Status.DELIVERY
        and session.current_screen == "DELIVERY"
        and session.total_payable == Decimal("245.00")
        and "245.00" in data_deliv.get("data", {}).get("total_amount", "")
    )
    check(7, "Navigation to DELIVERY Screen & FlowSession Total", t7_ok,
          f"Screen: {data_deliv.get('screen')}, Session Total: Rs.{session.total_payable}, Status: {session.status}")
except Exception as e:
    check(7, "Navigation to DELIVERY Screen", False, str(e))


# ── TEST 8: Navigate to SUMMARY -> Full Recap ────────────────────────────────
try:
    req_sum = rf.post("/webhook/flow-data-exchange/", data=json.dumps({
        "action": "data_exchange",
        "screen": "DELIVERY",
        "flow_token": str(session.flow_token),
        "data": {
            "product_id": "prod_16",
            "customer_name": "Prakash Raji",
            "delivery_phone": "918807856058",
            "delivery_address": "42 Farm Market Lane, Anna Nagar",
            "payment_mode": "COD"
        }
    }), content_type="application/json")
    resp_sum = flow_view(req_sum)
    data_sum = resp_sum.data

    session.refresh_from_db()
    t8_ok = (
        data_sum.get("screen") == "SUMMARY"
        and data_sum.get("data", {}).get("customer_name") == "Prakash Raji"
        and data_sum.get("data", {}).get("payment_mode") == "Cash on Delivery (COD)"
        and session.full_name == "Prakash Raji"
        and session.status == FlowSession.Status.SUMMARY
    )
    check(8, "Navigation to SUMMARY Screen & Validation", t8_ok,
          f"Recap Name: {data_sum.get('data', {}).get('customer_name')}, Payment: {data_sum.get('data', {}).get('payment_mode')}")
except Exception as e:
    check(8, "Navigation to SUMMARY Screen", False, str(e))


# ── TEST 9: Final Submit -> Order Creation & Complete ────────────────────────
try:
    req_comp = rf.post("/webhook/flow-data-exchange/", data=json.dumps({
        "action": "data_exchange",
        "screen": "SUMMARY",
        "flow_token": str(session.flow_token),
        "data": {
            "action": "complete",
            "product_id": "prod_16",
            "quantity": "3 kg",
            "total_amount": "₹ 245.00",
            "customer_name": "Prakash Raji",
            "delivery_phone": "918807856058",
            "delivery_address": "42 Farm Market Lane, Anna Nagar"
        }
    }), content_type="application/json")
    resp_comp = flow_view(req_comp)
    data_comp = resp_comp.data

    session.refresh_from_db()
    order = Order.objects.filter(session=session).first()
    t9_ok = (
        data_comp.get("screen") == "COMPLETE"
        and session.status == FlowSession.Status.COMPLETE
        and order is not None
        and order.total_payable == Decimal("245.00")
        and order.customer_name == "Prakash Raji"
    )
    check(9, "Final Submit: Order Created & Session Marked COMPLETE", t9_ok,
          f"Created Order #{order.id} for {order.customer_name}, Total: Rs.{order.total_payable}, Session Status: {session.status}")
except Exception as e:
    check(9, "Final Submit", False, str(e))


# ── TEST 10: Flow Crypto RSA-OAEP + AES-128-GCM Roundtrip ─────────────────────
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives import hashes
    import base64

    private_key = _load_rsa_private_key()
    public_key = private_key.public_key()

    # Generate AES-128 key and 12-byte IV
    aes_key = AESGCM.generate_key(bit_length=128)
    iv = os.urandom(12)

    # Encrypt AES key using RSA public key (mimicking WhatsApp client)
    encrypted_aes_key = public_key.encrypt(
        aes_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )

    # Encrypt sample payload with AES-GCM
    sample_payload = {"action": "ping"}
    aesgcm = AESGCM(aes_key)
    encrypted_flow_data = aesgcm.encrypt(iv, json.dumps(sample_payload).encode("utf-8"), None)

    encrypted_req_body = {
        "encrypted_aes_key": base64.b64encode(encrypted_aes_key).decode("utf-8"),
        "encrypted_flow_data": base64.b64encode(encrypted_flow_data).decode("utf-8"),
        "initial_vector": base64.b64encode(iv).decode("utf-8")
    }

    # Decrypt using flow_crypto
    decrypted_json, decrypted_key, decrypted_iv = decrypt_flow_request(encrypted_req_body)

    # Re-encrypt response
    sample_response = {"data": {"status": "active"}}
    encrypted_response_b64 = encrypt_flow_response(sample_response, decrypted_key, decrypted_iv)

    # Verify response decryption with bitwise-inverted IV
    flipped_iv = bytes(b ^ 0xFF for b in iv)
    cipher_bytes = base64.b64decode(encrypted_response_b64)
    decrypted_resp_bytes = aesgcm.decrypt(flipped_iv, cipher_bytes, None)
    decrypted_resp_json = json.loads(decrypted_resp_bytes.decode("utf-8"))

    t10_ok = (
        decrypted_json == sample_payload
        and decrypted_resp_json == sample_response
    )
    check(10, "Flow Crypto (RSA-OAEP + AES-128-GCM with Inverted IV Roundtrip)", t10_ok,
          "Inbound payload decrypted and outbound response re-encrypted successfully per Meta spec")
except Exception as e:
    check(10, "Flow Crypto", False, str(e))


# ── TEST 11: Celery Stale Sessions Cleanup Task ──────────────────────────────
try:
    from django.utils import timezone
    from datetime import timedelta

    # Create dummy stale session older than 25 hours
    old_session = FlowSession.objects.create(
        customer_phone="919999999999",
        status=FlowSession.Status.DRAFT
    )
    # Backdate created_at
    FlowSession.objects.filter(pk=old_session.pk).update(
        created_at=timezone.now() - timedelta(hours=25)
    )

    result = cleanup_stale_sessions_task()
    remaining = FlowSession.objects.filter(pk=old_session.pk).exists()
    t11_ok = (not remaining and result.get("cleaned_sessions", 0) >= 1)
    check(11, "Celery cleanup_stale_sessions_task", t11_ok,
          f"Cleaned up stale sessions: {result.get('cleaned_sessions')}")
except Exception as e:
    check(11, "Celery cleanup_stale_sessions_task", False, str(e))


# ── TEST 12: GET /webhook/flow-data-exchange/health/ Healthcheck Endpoint ────
try:
    health_view = FlowHealthCheckView.as_view()
    req_health = rf.get("/webhook/flow-data-exchange/health/")
    resp_health = health_view(req_health)
    data_health = resp_health.data

    # Also test GET on FlowDataExchangeView
    req_exchange_get = rf.get("/webhook/flow-data-exchange/")
    resp_exchange_get = flow_view(req_exchange_get)

    t12_ok = (
        resp_health.status_code == 200
        and data_health.get("status") == "ok"
        and data_health.get("service") == "whatsapp_flow_data_exchange"
        and "testing_mode" in data_health
        and resp_exchange_get.status_code == 200
    )
    check(12, "Unencrypted Health Check Endpoint (GET /webhook/flow-data-exchange/health/)", t12_ok,
          f"HTTP 200 OK: {data_health}")
except Exception as e:
    check(12, "Unencrypted Health Check Endpoint", False, str(e))


# ── TEST 13: TESTING_MODE Draft Mode Keyword Trigger (No Graph API Call) ──────
try:
    import unittest.mock as mock

    # Force TESTING_MODE = True
    original_testing_mode = getattr(settings, "TESTING_MODE", True)
    settings.TESTING_MODE = True

    with mock.patch("whatsapp.views.send_flow_trigger_message") as mock_send:
        msg_body = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "1965689270778996",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "messages": [{
                            "from": "918807856058",
                            "id": "wamid.test_draft_001",
                            "timestamp": "1788500100",
                            "text": {"body": "hello fresh produce"},
                            "type": "text"
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        req_draft = rf.post("/webhook/messages/", data=json.dumps(msg_body), content_type="application/json")
        resp_draft = view(req_draft)

        # In testing mode, send_flow_trigger_message must NOT have been called
        t13_ok = (
            resp_draft.status_code == 200
            and not mock_send.called
        )
        check(13, "TESTING_MODE=True Suppresses Graph API Call (Avoids Error 139000)", t13_ok,
              f"HTTP 200 returned, send_flow_trigger_message.called={mock_send.called} (Bypassed in draft mode)")

    settings.TESTING_MODE = original_testing_mode
except Exception as e:
    check(13, "TESTING_MODE Suppresses Graph API Call", False, str(e))


print("\n" + "=" * 70)
print(f"  TOTAL: {passed + failed} | PASSED: {passed} | FAILED: {failed}")
print("=" * 70 + "\n")

if failed > 0:
    sys.exit(1)
