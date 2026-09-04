"""
update_flow_metadata.py
───────────────────────
Updates an existing WhatsApp Flow's metadata (name, categories, etc.) via Meta Graph API:

POST https://graph.facebook.com/v21.0/{FLOW_ID}
Headers:
    Authorization: Bearer {ACCESS_TOKEN}
    Content-Type: application/json
Payload:
    {
        "name": "New flow name",
        "categories": ["OTHER"]
    }

Usage:
    python update_flow_metadata.py
    python update_flow_metadata.py "Fresh Trace Farm Store"
    python update_flow_metadata.py "Fresh Trace Farm Store" --categories OTHER ORDER_DETAILS
"""

import sys
import json
import requests
from decouple import config


def update_flow_metadata(new_name: str = None, categories: list = None, flow_id: str = None):
    token = config("WHATSAPP_ACCESS_TOKEN", default=config("WHATSAPP_TOKEN", default=""))
    flow_id = flow_id or config("WHATSAPP_FLOW_ID", default=config("FLOW_ID", default="1422173683118152"))
    api_version = config("WHATSAPP_API_VERSION", default="v21.0")

    url = f"https://graph.facebook.com/{api_version}/{flow_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {}
    if new_name:
        payload["name"] = new_name
    if categories:
        payload["categories"] = categories

    if not payload:
        payload["name"] = "Fresh Trace Farm Market Flow"

    print("=" * 68)
    print("  UPDATING WHATSAPP FLOW METADATA VIA GRAPH API")
    print("=" * 68)
    print(f"URL     : {url}")
    print(f"Flow ID : {flow_id}")
    print(f"Payload : {json.dumps(payload, indent=2)}")
    print("-" * 68)

    response = requests.post(url, headers=headers, json=payload)
    print(f"HTTP Status: {response.status_code}")
    print(f"Response   : {response.text}")
    print("=" * 68)

    if response.status_code == 200:
        res_json = response.json()
        if res_json.get("success"):
            print("\n[OK] SUCCESS: Flow metadata updated successfully!\n")
            return True

    return False


if __name__ == "__main__":
    flow_name = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "Fresh Trace Farm Market Flow"
    cats = None
    if "--categories" in sys.argv:
        cat_idx = sys.argv.index("--categories")
        cats = sys.argv[cat_idx + 1:]

    update_flow_metadata(new_name=flow_name, categories=cats)
