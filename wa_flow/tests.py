"""
wa_flow/tests.py
────────────────
Unit and integration tests for WhatsApp Webhook and Flow endpoints:
- Webhook GET handshake verification.
- Webhook POST message greeting routing.
- Flow crypto RSA-OAEP + AES-GCM decryption and inverted-IV response encryption.
- Flow action routing: INIT, products_selected, delivery_selected, order_confirmed.
- Error handling (HTTP 421 on crypto/payload failure).
"""

import base64
import json
import os
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)
from django.conf import settings
from django.test import Client, TestCase
from django.urls import reverse

from .flow_crypto import decrypt_flow_request, encrypt_flow_response
from .services import create_order, handle_flow_action


class WaFlowWebhookTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.verify_token = getattr(settings, "VERIFY_TOKEN", "fresh_trace_wa_c5a23fd481477ef350e8944373ddfe3a")

    def test_webhook_get_success(self):
        """Test GET /webhook/ verification handshake with correct token."""
        response = self.client.get(
            reverse("wa_flow:webhook"),
            {
                "hub.mode": "subscribe",
                "hub.verify_token": self.verify_token,
                "hub.challenge": "1155993300",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode("utf-8"), "1155993300")

    def test_webhook_get_forbidden(self):
        """Test GET /webhook/ verification handshake with invalid token."""
        response = self.client.get(
            reverse("wa_flow:webhook"),
            {
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong_token",
                "hub.challenge": "1155993300",
            },
        )
        self.assertEqual(response.status_code, 403)

    @patch("wa_flow.views.send_flow_message")
    def test_webhook_post_triggers_flow_on_hi(self, mock_send_flow):
        """Test POST /webhook/ with message 'hi' triggers send_flow_message."""
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "1965689270778996",
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "messages": [
                                    {
                                        "from": "918807856058",
                                        "id": "wamid.test123",
                                        "timestamp": "1725345000",
                                        "text": {"body": "  Hi  "},
                                        "type": "text",
                                    }
                                ],
                            },
                            "field": "messages",
                        }
                    ],
                }
            ],
        }
        response = self.client.post(
            reverse("wa_flow:webhook"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        mock_send_flow.assert_called_once_with("918807856058")

    @patch("wa_flow.views.send_flow_message")
    def test_webhook_post_ignores_other_text(self, mock_send_flow):
        """Test POST /webhook/ with other text does not trigger flow."""
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "918807856058",
                                        "text": {"body": "where is my order"},
                                        "type": "text",
                                    }
                                ]
                            }
                        }
                    ]
                }
            ],
        }
        response = self.client.post(
            reverse("wa_flow:webhook"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        mock_send_flow.assert_not_called()


class WaFlowCryptoAndEndpointTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Generate dynamic test RSA key pair
        cls.test_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.test_public_key = cls.test_private_key.public_key()
        cls.test_pem = cls.test_private_key.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.PKCS8,
            encryption_algorithm=NoEncryption(),
        ).decode("utf-8")

    def setUp(self):
        self.client = Client()

    def _encrypt_for_flow(self, data_dict: dict):
        """Helper to simulate WhatsApp encrypting a request to the flow endpoint."""
        aes_key = os.urandom(16)
        iv = os.urandom(12)

        # Encrypt AES key with RSA-OAEP SHA-256
        encrypted_aes_key = self.test_public_key.encrypt(
            aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )

        # Encrypt payload with AES-128-GCM
        payload_bytes = json.dumps(data_dict).encode("utf-8")
        aesgcm = AESGCM(aes_key)
        encrypted_flow_data = aesgcm.encrypt(iv, payload_bytes, None)

        body = {
            "encrypted_aes_key": base64.b64encode(encrypted_aes_key).decode("utf-8"),
            "encrypted_flow_data": base64.b64encode(encrypted_flow_data).decode("utf-8"),
            "initial_vector": base64.b64encode(iv).decode("utf-8"),
        }
        return body, aes_key, iv

    def _decrypt_flow_response(self, b64_response: str, aes_key: bytes, iv: bytes) -> dict:
        """Helper to decrypt the flow response using the inverted IV."""
        flipped_iv = bytes(b ^ 0xFF for b in iv)
        ciphertext = base64.b64decode(b64_response)
        aesgcm = AESGCM(aes_key)
        decrypted_bytes = aesgcm.decrypt(flipped_iv, ciphertext, None)
        return json.loads(decrypted_bytes.decode("utf-8"))

    def test_flow_init_action(self):
        """Test INIT action returns PRODUCTS screen."""
        with patch.object(settings, "FLOW_PRIVATE_KEY_PEM", self.test_pem):
            req_body, aes_key, iv = self._encrypt_for_flow({"action": "INIT"})
            response = self.client.post(
                reverse("wa_flow:flow_endpoint"),
                data=json.dumps(req_body),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 200)
            data = self._decrypt_flow_response(response.content.decode("utf-8"), aes_key, iv)
            self.assertEqual(data.get("screen"), "PRODUCTS")

    def test_flow_routing_complete_lifecycle(self):
        """Test full screen routing: products_selected -> delivery_selected -> order_confirmed."""
        with patch.object(settings, "FLOW_PRIVATE_KEY_PEM", self.test_pem):
            # 1. products_selected -> DELIVERY
            req_body, aes_key, iv = self._encrypt_for_flow({
                "action": "data_exchange",
                "screen": "PRODUCTS",
                "data": {
                    "trigger": "products_selected",
                    "produce_category": "Fresh Vegetables",
                    "quantity": "5",
                },
            })
            resp = self.client.post(
                reverse("wa_flow:flow_endpoint"),
                data=json.dumps(req_body),
                content_type="application/json",
            )
            self.assertEqual(resp.status_code, 200)
            data = self._decrypt_flow_response(resp.content.decode("utf-8"), aes_key, iv)
            self.assertEqual(data.get("screen"), "DELIVERY")
            self.assertEqual(data["data"]["produce_category"], "Fresh Vegetables")
            self.assertEqual(data["data"]["quantity"], "5")

            # 2. delivery_selected -> SUMMARY
            req_body, aes_key, iv = self._encrypt_for_flow({
                "action": "data_exchange",
                "screen": "DELIVERY",
                "data": {
                    "trigger": "delivery_selected",
                    "produce_category": "Fresh Vegetables",
                    "quantity": "5",
                    "address": "45 Farmer Lane, Nilgiris",
                    "delivery_date": "2026-09-08",
                },
            })
            resp = self.client.post(
                reverse("wa_flow:flow_endpoint"),
                data=json.dumps(req_body),
                content_type="application/json",
            )
            self.assertEqual(resp.status_code, 200)
            data = self._decrypt_flow_response(resp.content.decode("utf-8"), aes_key, iv)
            self.assertEqual(data.get("screen"), "SUMMARY")
            self.assertEqual(data["data"]["address"], "45 Farmer Lane, Nilgiris")

            # 3. order_confirmed -> COMPLETE
            req_body, aes_key, iv = self._encrypt_for_flow({
                "action": "data_exchange",
                "screen": "SUMMARY",
                "data": {
                    "trigger": "order_confirmed",
                    "produce_category": "Fresh Vegetables",
                    "quantity": "5",
                    "address": "45 Farmer Lane, Nilgiris",
                    "delivery_date": "2026-09-08",
                },
            })
            resp = self.client.post(
                reverse("wa_flow:flow_endpoint"),
                data=json.dumps(req_body),
                content_type="application/json",
            )
            self.assertEqual(resp.status_code, 200)
            data = self._decrypt_flow_response(resp.content.decode("utf-8"), aes_key, iv)
            self.assertEqual(data.get("screen"), "COMPLETE")
            self.assertTrue("ORD-" in data["data"]["order_id"])

    def test_flow_endpoint_returns_421_on_bad_data(self):
        """Test that invalid payload returns HTTP 421 per Meta specification."""
        response = self.client.post(
            reverse("wa_flow:flow_endpoint"),
            data=json.dumps({"bad": "payload"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 421)
