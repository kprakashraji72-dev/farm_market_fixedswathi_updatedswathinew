"""
whatsapp/flow_crypto.py
───────────────────────
Cryptographic helper functions implementing Meta WhatsApp Flows encryption spec:
1. RSA-OAEP (SHA-256) for decrypting the AES-128 symmetric key.
2. AES-128-GCM for decrypting inbound flow payload (ciphertext + 16-byte auth tag).
3. AES-128-GCM with bitwise-inverted IV (b ^ 0xFF) for encrypting outbound response.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any, Tuple

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from django.conf import settings

logger = logging.getLogger(__name__)


class FlowCryptoError(Exception):
    """Raised when decryption or encryption of a WhatsApp Flow payload fails."""
    pass


def _load_rsa_private_key():
    """
    Loads RSA private key from settings.WHATSAPP_FLOW_PRIVATE_KEY or file path.
    """
    pem_raw: str = getattr(settings, "WHATSAPP_FLOW_PRIVATE_KEY", "") or getattr(settings, "WHATSAPP_FLOW_PRIVATE_KEY_PEM", "") or ""
    
    if not pem_raw.strip():
        key_path = getattr(settings, "WHATSAPP_FLOW_PRIVATE_KEY_PATH", "whatsapp_flow_private.pem")
        # Check current dir and parent dir
        candidate_paths = [
            key_path,
            os.path.join(os.path.dirname(settings.BASE_DIR), key_path),
            os.path.join(settings.BASE_DIR, key_path),
        ]
        for path in candidate_paths:
            if os.path.exists(path):
                with open(path, "rb") as f:
                    return load_pem_private_key(f.read(), password=None)
        raise FlowCryptoError(
            "WHATSAPP_FLOW_PRIVATE_KEY is empty and no valid private key file was found."
        )

    formatted_pem = pem_raw.replace("\\n", "\n").strip().encode("utf-8")
    return load_pem_private_key(formatted_pem, password=None)


def decrypt_flow_request(body: dict[str, Any]) -> Tuple[dict[str, Any], bytes, bytes]:
    """
    Decrypts incoming WhatsApp Flow payload.

    Args:
        body: JSON dict containing 'encrypted_aes_key', 'encrypted_flow_data',
              and 'initial_vector'.

    Returns:
        tuple of (decrypted_json_data, aes_key_bytes, initial_vector_bytes)

    Raises:
        FlowCryptoError: on any missing field or decryption failure.
    """
    try:
        encrypted_aes_key_b64 = body["encrypted_aes_key"]
        encrypted_flow_data_b64 = body["encrypted_flow_data"]
        initial_vector_b64 = body["initial_vector"]
    except KeyError as err:
        logger.error("[FlowCrypto] Missing mandatory encryption field: %s", err)
        raise FlowCryptoError(f"Missing mandatory encryption field: {err}") from err

    try:
        private_key = _load_rsa_private_key()

        # 1. Decrypt AES-128 Key using RSA-OAEP with SHA-256
        encrypted_aes_key = base64.b64decode(encrypted_aes_key_b64)
        aes_key = private_key.decrypt(
            encrypted_aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )

        # 2. Base64 decode IV and flow payload
        iv = base64.b64decode(initial_vector_b64)
        encrypted_flow_data = base64.b64decode(encrypted_flow_data_b64)

        # 3. Decrypt AES-128-GCM (the last 16 bytes are the auth tag)
        aesgcm = AESGCM(aes_key)
        decrypted_bytes = aesgcm.decrypt(iv, encrypted_flow_data, None)
        decrypted_json = json.loads(decrypted_bytes.decode("utf-8"))

        return decrypted_json, aes_key, iv

    except Exception as exc:
        logger.exception("[FlowCrypto] Decryption failed: %s", exc)
        raise FlowCryptoError(f"Failed to decrypt Flow request: {exc}") from exc


def encrypt_flow_response(response_payload: dict[str, Any], aes_key: bytes, iv: bytes) -> str:
    """
    Encrypts outgoing WhatsApp Flow response using AES-128-GCM and a bitwise-inverted IV.

    Args:
        response_payload: The dictionary to be returned to WhatsApp.
        aes_key: The AES-128 symmetric key used during inbound decryption.
        iv: The original initial_vector from the inbound request.

    Returns:
        Base64-encoded ciphertext + 16-byte tag as a string.

    Raises:
        FlowCryptoError: on any encryption failure.
    """
    try:
        # Bitwise-inverted IV: flip every byte (b ^ 0xFF)
        flipped_iv = bytes(b ^ 0xFF for b in iv)

        # Encrypt with AES-128-GCM
        payload_bytes = json.dumps(response_payload).encode("utf-8")
        aesgcm = AESGCM(aes_key)
        encrypted_bytes = aesgcm.encrypt(flipped_iv, payload_bytes, None)

        # Return Base64 encoded ciphertext + tag
        return base64.b64encode(encrypted_bytes).decode("utf-8")

    except Exception as exc:
        logger.exception("[FlowCrypto] Response encryption failed: %s", exc)
        raise FlowCryptoError(f"Failed to encrypt Flow response: {exc}") from exc
