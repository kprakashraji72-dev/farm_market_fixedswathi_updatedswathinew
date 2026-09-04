"""
upload_draft_flow.py
────────────────────
Uploads flow.json to Meta's Flows API as multipart/form-data:

POST https://graph.facebook.com/v21.0/{FLOW_ID}/assets
Headers:
    Authorization: Bearer {ACCESS_TOKEN}
Form fields:
    name: "flow.json"
    asset_type: "FLOW_JSON"
    file: <file-stream> (type: application/json)
"""

import os
import sys
import requests
from decouple import config

def upload_flow_asset(flow_id: str = None, file_path: str = "wa_flow/flow_definitions/flow.json"):
    token = config("WHATSAPP_ACCESS_TOKEN", default=config("WHATSAPP_TOKEN", default=""))
    flow_id = flow_id or config("WHATSAPP_FLOW_ID", default=config("FLOW_ID", default="1422173683118152"))
    api_version = config("WHATSAPP_API_VERSION", default="v21.0")

    if not os.path.exists(file_path):
        print(f"[ERROR] File not found: {file_path}")
        return False

    url = f"https://graph.facebook.com/{api_version}/{flow_id}/assets"
    headers = {
        "Authorization": f"Bearer {token}"
    }

    print("=" * 68)
    print(f"  UPLOADING FLOW JSON ASSET TO META GRAPH API")
    print("=" * 68)
    print(f"URL       : {url}")
    print(f"Flow ID   : {flow_id}")
    print(f"File Path : {file_path} ({os.path.getsize(file_path)} bytes)")
    print("-" * 68)

    with open(file_path, "rb") as f:
        files = {
            "file": ("flow.json", f, "application/json")
        }
        data = {
            "name": "flow.json",
            "asset_type": "FLOW_JSON"
        }

        response = requests.post(url, headers=headers, data=data, files=files)

    print(f"HTTP Status: {response.status_code}")
    print(f"Response   : {response.text}")
    print("=" * 68)

    if response.status_code == 200:
        res_json = response.json()
        if res_json.get("success"):
            print("\n>>> SUCCESS: Flow JSON successfully uploaded and validated by Meta with 0 errors! <<<\n")
            return True

    return False

if __name__ == "__main__":
    flow_id_arg = sys.argv[1] if len(sys.argv) > 1 else None
    file_path_arg = sys.argv[2] if len(sys.argv) > 2 else "wa_flow/flow_definitions/flow.json"
    upload_flow_asset(flow_id_arg, file_path_arg)

