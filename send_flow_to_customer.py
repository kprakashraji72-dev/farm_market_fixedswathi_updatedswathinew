"""
send_flow_to_customer.py
────────────────────────
Quick script to dispatch the WhatsApp Farm Market Flow ('fram_check')
directly to a customer's WhatsApp number.

Usage:
    python send_flow_to_customer.py 918807856058
"""

import os
import sys
import django

# Setup Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "farm_market.settings")
django.setup()

from whatsapp_webhook.services import send_flow_message

def send_test_flow(phone_number: str):
    print(f"\n====================================================================")
    print(f"  DISPATCHING FARM MARKET FLOW TO: +{phone_number}")
    print(f"====================================================================")

    res = send_flow_message(
        to_phone=phone_number,
        body_text="Farm Fresh Produce\n\nHandpicked organic harvest delivered fresh from local farms. Choose your item below:",
        cta_text="Preview Flow",
        header_text="Fresh Trace Market",
        footer_text="Farm Fresh Delivery"
    )

    if res.get("success"):
        print(f"\n[SUCCESS] Flow message delivered to +{phone_number}.")
        print("Open your WhatsApp on your phone and tap the 'Order Fresh' button!\n")
    else:
        print(f"\n[FAILED TO SEND FLOW]:")
        print(res.get("error"))
        print("\nPlease check your WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID in .env\n")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_phone = sys.argv[1]
    else:
        target_phone = input("Enter customer phone number with country code (e.g. 919876543210): ").strip()

    if target_phone:
        send_test_flow(target_phone)
    else:
        print("No phone number provided.")
