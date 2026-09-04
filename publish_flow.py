"""
publish_flow.py
───────────────
Publishes a validated WhatsApp Flow from DRAFT status to PUBLISHED status via Meta Graph API:

POST https://graph.facebook.com/v21.0/{FLOW_ID}/publish
Headers:
    Authorization: Bearer {ACCESS_TOKEN}

Once published:
- The Flow is live and can be received by ANY WhatsApp user without Error 139000.
- Live keyword triggers ("hi") will successfully deliver the interactive Flow message.
"""

import sys
import requests
from decouple import config


def publish_flow(flow_id: str = None):
    token = config("WHATSAPP_ACCESS_TOKEN", default=config("WHATSAPP_TOKEN", default=""))
    flow_id = flow_id or config("WHATSAPP_FLOW_ID", default=config("FLOW_ID", default="1422173683118152"))
    api_version = config("WHATSAPP_API_VERSION", default="v21.0")

    url = f"https://graph.facebook.com/{api_version}/{flow_id}/publish"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    print("=" * 68)
    print("  PUBLISHING WHATSAPP FLOW VIA META GRAPH API")
    print("=" * 68)
    print(f"URL     : {url}")
    print(f"Flow ID : {flow_id}")
    print("-" * 68)

    response = requests.post(url, headers=headers)
    print(f"HTTP Status: {response.status_code}")
    print(f"Response   : {response.text}")
    print("=" * 68)

    if response.status_code == 200:
        res_json = response.json()
        if res_json.get("success"):
            print("\n[OK] SUCCESS: Flow is now officially PUBLISHED!")
            print("You can now trigger the Flow live from WhatsApp with 'hi'.\n")
            return True

    return False


if __name__ == "__main__":
    target_flow = sys.argv[1] if len(sys.argv) > 1 else None
    publish_flow(target_flow)
