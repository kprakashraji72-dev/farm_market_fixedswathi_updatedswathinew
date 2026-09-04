"""
flows_api.py
────────────
Comprehensive Meta WhatsApp Flows API Client & CLI implementing all official
Meta Flows API operations with automatic .env configuration:

Variables:
    - BASE_URL: https://graph.facebook.com/{API_VERSION}
    - ACCESS_TOKEN: Bearer token from .env
    - WABA_ID: WhatsApp Business Account ID (e.g. 1965689270778996)
    - PHONE_NUMBER_ID: Phone Number ID (e.g. 1297443690119359)
    - FLOW_ID: Target Flow ID (e.g. 1422173683118152)

Usage:
    python flows_api.py status               # Check flow status & metadata
    python flows_api.py list                 # List all flows under WABA
    python flows_api.py assets               # List assets attached to the Flow
    python flows_api.py upload-json          # Upload flow.json definition
    python flows_api.py update-name "Name"   # Update flow name
    python flows_api.py publish              # Publish flow
    python flows_api.py export-postman       # Generate Postman Environment JSON
"""

import os
import sys
import json
import requests
from decouple import config

# ── Load Required API Variables ──────────────────────────────────────────────
API_VERSION = config("WHATSAPP_API_VERSION", default="v21.0")
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"
ACCESS_TOKEN = config("WHATSAPP_ACCESS_TOKEN", default=config("WHATSAPP_TOKEN", default=""))
WABA_ID = config("WHATSAPP_WABA_ID", default="1965689270778996")
PHONE_NUMBER_ID = config("WHATSAPP_PHONE_NUMBER_ID", default="1297443690119359")
FLOW_ID = config("WHATSAPP_FLOW_ID", default="1422173683118152")

HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
}


def print_header(title: str):
    print("\n" + "=" * 68)
    print(f"  {title}")
    print("=" * 68)
    print(f"BASE_URL        : {BASE_URL}")
    print(f"WABA_ID         : {WABA_ID}")
    print(f"PHONE_NUMBER_ID : {PHONE_NUMBER_ID}")
    print(f"FLOW_ID         : {FLOW_ID}")
    print("-" * 68)


def get_flow_status(flow_id: str = None):
    """GET /{FLOW_ID} - Retrieves Flow metadata and publishing status."""
    target_id = flow_id or FLOW_ID
    print_header(f"RETRIEVING FLOW DETAILS: {target_id}")
    url = f"{BASE_URL}/{target_id}?fields=id,name,status,categories,validation_errors,json_version,data_api_version,endpoint_uri"
    res = requests.get(url, headers=HEADERS)
    print(f"HTTP Status: {res.status_code}")
    print("Response:\n" + json.dumps(res.json(), indent=2))
    return res.json()


def list_flows():
    """GET /{WABA_ID}/flows - Lists all Flows belonging to the WABA."""
    print_header(f"LISTING ALL FLOWS UNDER WABA: {WABA_ID}")
    url = f"{BASE_URL}/{WABA_ID}/flows?fields=id,name,status,categories"
    res = requests.get(url, headers=HEADERS)
    print(f"HTTP Status: {res.status_code}")
    print("Response:\n" + json.dumps(res.json(), indent=2))
    return res.json()


def get_flow_assets(flow_id: str = None):
    """GET /{FLOW_ID}/assets - Lists assets (flow.json) attached to the Flow."""
    target_id = flow_id or FLOW_ID
    print_header(f"RETRIEVING ASSETS FOR FLOW: {target_id}")
    url = f"{BASE_URL}/{target_id}/assets"
    res = requests.get(url, headers=HEADERS)
    print(f"HTTP Status: {res.status_code}")
    print("Response:\n" + json.dumps(res.json(), indent=2))
    return res.json()


def upload_flow_json(file_path: str = "wa_flow/flow_definitions/flow.json", flow_id: str = None):
    """POST /{FLOW_ID}/assets - Uploads flow.json via multipart/form-data."""
    target_id = flow_id or FLOW_ID
    print_header(f"UPLOADING FLOW JSON ASSET: {file_path}")
    if not os.path.exists(file_path):
        print(f"[ERROR] File not found: {file_path}")
        return False

    url = f"{BASE_URL}/{target_id}/assets"
    with open(file_path, "rb") as f:
        files = {"file": ("flow.json", f, "application/json")}
        data = {"name": "flow.json", "asset_type": "FLOW_JSON"}
        res = requests.post(url, headers=HEADERS, data=data, files=files)

    print(f"HTTP Status: {res.status_code}")
    print("Response:\n" + json.dumps(res.json(), indent=2))
    return res.status_code == 200


def update_flow_name(new_name: str, flow_id: str = None):
    """POST /{FLOW_ID} - Updates Flow name/metadata."""
    target_id = flow_id or FLOW_ID
    print_header(f"UPDATING FLOW METADATA: {new_name}")
    url = f"{BASE_URL}/{target_id}"
    payload = {"name": new_name}
    res = requests.post(url, headers={**HEADERS, "Content-Type": "application/json"}, json=payload)
    print(f"HTTP Status: {res.status_code}")
    print("Response:\n" + json.dumps(res.json(), indent=2))
    return res.status_code == 200


def publish_flow(flow_id: str = None):
    """POST /{FLOW_ID}/publish - Publishes the Flow."""
    target_id = flow_id or FLOW_ID
    print_header(f"PUBLISHING FLOW: {target_id}")
    url = f"{BASE_URL}/{target_id}/publish"
    res = requests.post(url, headers={**HEADERS, "Content-Type": "application/json"})
    print(f"HTTP Status: {res.status_code}")
    print("Response:\n" + json.dumps(res.json(), indent=2))
    return res.status_code == 200


def export_postman_environment(out_file: str = "whatsapp_flows_postman_environment.json"):
    """Generates a ready-to-import Postman Environment file."""
    postman_env = {
        "id": "fresh-trace-flows-env",
        "name": "WhatsApp Flows API (Fresh Trace)",
        "values": [
            {
                "key": "BASE-URL",
                "value": BASE_URL,
                "type": "default",
                "enabled": True
            },
            {
                "key": "ACCESS-TOKEN",
                "value": ACCESS_TOKEN,
                "type": "secret",
                "enabled": True
            },
            {
                "key": "WABA-ID",
                "value": WABA_ID,
                "type": "default",
                "enabled": True
            },
            {
                "key": "PHONE-NUMBER-ID",
                "value": PHONE_NUMBER_ID,
                "type": "default",
                "enabled": True
            },
            {
                "key": "FLOW-ID",
                "value": FLOW_ID,
                "type": "default",
                "enabled": True
            }
        ],
        "_postman_variable_scope": "environment",
        "_postman_exported_at": "2026-09-04T07:00:00.000Z",
        "_postman_exported_using": "Antigravity Meta Flows Client"
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(postman_env, f, indent=2)

    print("\n" + "=" * 68)
    print(f"  POSTMAN ENVIRONMENT EXPORTED SUCCESSFULLY")
    print("=" * 68)
    print(f"File: {os.path.abspath(out_file)}")
    print("\nImport this JSON file into Postman under 'Environments' to make calls")
    print("with Meta's official WhatsApp Flows API Postman Collection!")
    print("=" * 68 + "\n")


if __name__ == "__main__":
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else "status"

    if cmd in ("status", "info"):
        get_flow_status()
    elif cmd in ("list", "flows"):
        list_flows()
    elif cmd in ("assets", "asset"):
        get_flow_assets()
    elif cmd in ("upload", "upload-json"):
        upload_flow_json()
    elif cmd in ("update", "update-name"):
        name_arg = sys.argv[2] if len(sys.argv) > 2 else "Fresh Trace Farm Market Flow"
        update_flow_name(name_arg)
    elif cmd in ("publish",):
        publish_flow()
    elif cmd in ("postman", "export-postman"):
        export_postman_environment()
    else:
        print("Usage: python flows_api.py [status|list|assets|upload-json|update-name|publish|export-postman]")
