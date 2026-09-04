import sys
import time
import os

LOG_FILE = "incoming_whatsapp_messages.txt"

def show_all():
    if not os.path.exists(LOG_FILE) or os.path.getsize(LOG_FILE) == 0:
        print("\nNo messages received yet. Send a message on WhatsApp to see it here!\n")
        return
    print("\n" + "=" * 68)
    print("           ALL INCOMING CUSTOMER WHATSAPP MESSAGES")
    print("=" * 68)
    with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                print("  " + line.strip())
            except Exception:
                safe_line = line.strip().encode(sys.stdout.encoding or "ascii", errors="replace").decode(sys.stdout.encoding or "ascii")
                print("  " + safe_line)
    print("=" * 68 + "\n")

if __name__ == "__main__":
    show_all()
