import requests
import base64
import os
import json

from decouple import config

# Configuration
PHONE_NUMBER_ID = config("WHATSAPP_PHONE_NUMBER_ID", default="1297443690119359")
ACCESS_TOKEN = config("WHATSAPP_ACCESS_TOKEN", default=config("WHATSAPP_TOKEN", default=""))


def upload_key():
    # Find the public key file
    key_path = 'whatsapp_flow_public.pem'
    
    if not os.path.exists(key_path):
        print(f"❌ ERROR: {key_path} not found!")
        print("\nPlease make sure public_python.pem exists in the project root.")
        print("Run: generate_flow_keys.bat")
        return
    
    # Read the public key
    with open(key_path, 'r') as f:
        public_key_pem = f.read().strip()
    
    # Verify it's a valid public key
    if not public_key_pem.startswith('-----BEGIN PUBLIC KEY-----'):
        print("❌ ERROR: This doesn't look like a valid public key!")
        print("Make sure you're using public_python.pem (not private_python.pem)")
        return
    
    print("=" * 60)
    print("Uploading Public Key to WhatsApp/Meta")
    print("=" * 60)
    print(f"\nKey file: {key_path}")
    print(f"Key size: {len(public_key_pem)} bytes")
    print(f"\nPhone Number ID: {PHONE_NUMBER_ID}")
    
    # Try Method 1: Upload with full PEM format
    print("\n[Method 1] Trying with full PEM format...")
    url = f"https://graph.facebook.com/v24.0/{PHONE_NUMBER_ID}/whatsapp_business_encryption"
    
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "business_public_key": public_key_pem
    }
    
    response = requests.post(url, headers=headers, json=payload)
    
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        print("\n" + "=" * 60)
        print("[OK] SUCCESS! Public key uploaded to WhatsApp")
        print("=" * 60)
        result = response.json()
        print("\nResponse:", json.dumps(result, indent=2))
        print_next_steps()
        return
    
    print(f"Response: {response.text}")
    
    # Try Method 2: Upload with base64 content only (no headers)
    print("\n[Method 2] Trying with base64 content only...")
    key_lines = public_key_pem.split('\n')
    key_content = ''.join([
        line for line in key_lines 
        if not line.startswith('-----')
    ])
    
    payload = {
        "business_public_key": key_content
    }
    
    response = requests.post(url, headers=headers, json=payload)
    
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        print("\n" + "=" * 60)
        print("[OK] SUCCESS! Public key uploaded to WhatsApp")
        print("=" * 60)
        result = response.json()
        print("\nResponse:", json.dumps(result, indent=2))
        print_next_steps()
        return
    
    print(f"Response: {response.text}")
    
    # Both methods failed
    print("\n" + "=" * 60)
    print("[FAILED] Both upload methods failed")
    print("=" * 60)
    print("\nThe API is rejecting the key. This could mean:")
    print("1. The access token doesn't have the right permissions")
    print("2. The phone number ID is incorrect")
    print("3. WhatsApp Flow encryption must be configured via UI")
    print("\n" + "=" * 60)
    print("MANUAL UPLOAD INSTRUCTIONS")
    print("=" * 60)
    print("\nPlease upload the key manually:")
    print("\n1. Go to: https://business.facebook.com/")
    print("2. Select your WhatsApp Business Account")
    print("3. Go to: Account Tools -> Phone Numbers")
    print("4. Click on your phone number")
    print("5. Go to: WhatsApp Manager -> Flows")
    print("6. Select your Flow")
    print("7. Go to: Settings -> Endpoint")
    print("8. Click 'Upload Public Key'")
    print(f"9. Upload this file: {os.path.abspath(key_path)}")
    print("10. Save changes")
    print("\nAfter uploading:")
    print("- Wait 5-10 minutes for the key to propagate")
    print("- Test your Flow from WhatsApp")

def print_next_steps():
    print("\n" + "=" * 60)
    print("Next Steps:")
    print("=" * 60)
    print("1. Wait a moment for WhatsApp to update the key")
    print("2. Wire ngrok endpoint to Flow in WhatsApp Manager")
    print("3. Click 'Preview Flow' to test interactively")

if __name__ == "__main__":
    try:
        upload_key()
    except KeyboardInterrupt:
        print("\n\nUpload cancelled by user")
    except Exception as e:
        print(f"\n[ERROR]: {e}")
        import traceback
        traceback.print_exc()