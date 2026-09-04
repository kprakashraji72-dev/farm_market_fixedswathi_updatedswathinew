"""
create_new_flow.py
──────────────────
Creates a brand new WhatsApp Flow in DRAFT status using Meta Graph API:

POST https://graph.facebook.com/v21.0/{WABA_ID}/flows
Headers:
    Authorization: Bearer {ACCESS_TOKEN}
    Content-Type: application/json
Payload:
    {
        "name": "fresh_trace_farm_market_v2",
        "categories": ["OTHER"],
        "flow_json": "<escaped JSON string>"
    }
"""

import json
import requests
from decouple import config

def create_flow(flow_name: str = "fresh_trace_market_flow"):
    token = config("WHATSAPP_ACCESS_TOKEN", default=config("WHATSAPP_TOKEN", default=""))
    waba_id = "1965689270778996"
    api_version = config("WHATSAPP_API_VERSION", default="v21.0")

    url = f"https://graph.facebook.com/{api_version}/{waba_id}/flows"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Read flow JSON file
    flow_file = "wa_flow/flow_definitions/flow.json"
    with open(flow_file, "r", encoding="utf-8") as f:
        flow_content = f.read()

    payload = {
        "name": flow_name,
        "categories": ["OTHER"],
        "flow_json": flow_content
    }

    print("=" * 68)
    print(f"  CREATING NEW DRAFT FLOW VIA GRAPH API")
    print("=" * 68)
    print(f"URL     : {url}")
    print(f"WABA ID : {waba_id}")
    print(f"Name    : {flow_name}")
    print("-" * 68)

    response = requests.post(url, headers=headers, json=payload)
    print(f"HTTP Status: {response.status_code}")
    print(f"Response   : {response.text}")
    print("=" * 68)

    if response.status_code in (200, 201):
        res_data = response.json()
        new_flow_id = res_data.get("id")
        print(f"\n🎉 NEW FLOW CREATED SUCCESSFULLY!")
        print(f"New Flow ID: {new_flow_id}")
        return new_flow_id

    return None

if __name__ == "__main__":
    create_flow()
