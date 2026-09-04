"""
create_simple_flow.py
─────────────────────
Implements Meta's single-request Flow creation API call:

curl -X POST '{BASE-URL}/{WABA-ID}/flows' \\
  --header 'Authorization: Bearer {ACCESS-TOKEN}' \\
  --header "Content-Type: application/json" \\
  --data '{
    "name": "My first flow",
    "categories": [ "OTHER" ],
    "flow_json": "{\"version\":\"7.3\",\"screens\":[{\"id\":\"WELCOME_SCREEN\",\"layout\":{\"type\":\"SingleColumnLayout\",\"children\":[{\"type\":\"TextHeading\",\"text\":\"Hello World\"},{\"type\":\"Footer\",\"label\":\"Complete\",\"on-click-action\":{\"name\":\"complete\",\"payload\":{}}}]},\"title\":\"Welcome\",\"terminal\":true,\"success\":true,\"data\":{}}]}",
    "publish": true
  }'

Usage:
    python create_simple_flow.py
    python create_simple_flow.py --draft      # Create in DRAFT mode without "publish": true
    python create_simple_flow.py --v5         # Use version 5.0 instead of 7.3
"""

import sys
import json
import time
import requests
from decouple import config


def create_simple_flow(name: str = None, publish: bool = True, version: str = "7.3"):
    token = config("WHATSAPP_ACCESS_TOKEN", default=config("WHATSAPP_TOKEN", default=""))
    waba_id = config("WHATSAPP_WABA_ID", default="1965689270778996")
    api_version = config("WHATSAPP_API_VERSION", default="v21.0")

    if not name or name == "My first flow":
        name = f"My first flow {int(time.time()) % 10000}"

    url = f"https://graph.facebook.com/{api_version}/{waba_id}/flows"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    flow_json_dict = {

        "version": version,
        "screens": [
            {
                "id": "WELCOME_SCREEN",
                "title": "Welcome",
                "terminal": True,
                "success": True,
                "data": {},
                "layout": {
                    "type": "SingleColumnLayout",
                    "children": [
                        {"type": "TextHeading", "text": "Hello World"},
                        {
                            "type": "Footer",
                            "label": "Complete",
                            "on-click-action": {
                                "name": "complete",
                                "payload": {}
                            }
                        }
                    ]
                }
            }
        ]
    }

    payload = {
        "name": name,
        "categories": ["OTHER"],
        "flow_json": json.dumps(flow_json_dict)
    }

    if publish:
        payload["publish"] = True

    print("=" * 68)
    print("  CREATING FLOW VIA META GRAPH API (Single Request)")
    print("=" * 68)
    print(f"URL       : {url}")
    print(f"WABA ID   : {waba_id}")
    print(f"Name      : {name}")
    print(f"Version   : {version}")
    print(f"Publish   : {publish}")
    print("-" * 68)

    response = requests.post(url, headers=headers, json=payload)
    print(f"HTTP Status: {response.status_code}")
    print(f"Response   : {response.text}")
    print("=" * 68)

    if response.status_code in (200, 201):
        res_json = response.json()
        print("\n[OK] Flow created successfully!")
        print(f"Flow ID: {res_json.get('id')}\n")
        return res_json.get("id")

    return None


if __name__ == "__main__":
    is_publish = "--draft" not in sys.argv
    json_version = "5.0" if "--v5" in sys.argv else "7.3"
    flow_title = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "My first flow"

    create_simple_flow(name=flow_title, publish=is_publish, version=json_version)
