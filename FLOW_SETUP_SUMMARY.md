# WhatsApp Flow & Backend Integration — Project Handover Summary

**Date:** September 3, 2026  
**Project:** Fresh Trace Farm Market  
**Flow Architecture:** 4-Screen WhatsApp Flow (`PRODUCTS` ➔ `DELIVERY` ➔ `SUMMARY` ➔ `COMPLETE`)

---

## 1. What Was Built & Saved

### A. Data Models & Database Migrations (`wa_flow/`)
- **`Category` (`wa_flow/models.py`)**:
  - Slugs: `cat_veg` (Vegetables), `cat_fruits` (Fruits), `cat_greens` (Greens).
- **`Product` (`wa_flow/models.py`)**:
  - Seeded products:
    - Ooty Red Carrot (₹80.00/kg)
    - Fresh Orange Carrot (₹75.00/kg)
    - Regular Carrot (₹70.00/kg)
    - Organic Tomatoes (₹40.00/kg)
    - Farm Fresh Potato (₹40.00/kg)
    - Beetroot (₹45.00/kg)
    - Fruits & Organic Greens
- **`Quantity`**:
  - Fixed options: `qty_1` (1 kg), `qty_2` (2 kg), `qty_3` (3 kg), `qty_5` (5 kg Family Pack).
- **`Order` (`wa_flow/models.py`)**:
  - Fields: `product_id`, `quantity_label`, `unit_price`, `subtotal`, fixed `delivery_fee` (₹5.00), `total_amount`, `customer_name`, `delivery_phone`, `delivery_address`, `payment_mode` (`COD` / `UPI`), `status` (`CONFIRMED`), `created_at`.
- **Migrations Applied**:
  - `0001_initial.py` — Database schema creation.
  - `0002_seed_flow_products.py` — Seeded categories and catalog produce.

---

### B. Encrypted Flow Endpoint (`/flow-endpoint/` & `/whatsapp/flow/`)
- **Cryptographic Engine (`wa_flow/flow_crypto.py`)**:
  - Decrypts incoming payloads using **RSA-OAEP (SHA-256)** for the AES key and **AES-128-GCM** for the payload.
  - Encrypts outbound responses using the same AES key with a **bitwise-inverted IV**.
  - Returns **HTTP 421** on any decryption/key mismatch (per Meta's specification).
- **Screen Navigation Contract (`wa_flow/services.py`)**:
  1. `action == "INIT"`: Queries DB and returns `PRODUCTS` screen with categories, produce items with prices, and quantities.
  2. `on-select-action` (Dropdowns): Recalculates `unit_price`, `subtotal = price * multiplier`, `delivery_fee = ₹ 5.00`, and `total_amount`, returning updated `"₹ XX.XX"` currency strings live.
  3. `continue_to_delivery`: Transitions to `DELIVERY` screen with selected item details and `payment_mode="COD"`.
  4. Footer `Review Summary`: Validates phone number (10 digits), maps payment mode (`Cash on Delivery (COD)` / `UPI on Delivery`), and transitions to `SUMMARY`.
  5. Footer `Confirm Order`: Saves the order to the database with a unique `ORD-{id}` tracking number and transitions to `COMPLETE`.

---

### C. Webhook Handling (`/webhook/` & `/webhook/whatsapp/`)
- **GET Handshake**: Verifies `hub.mode`, `hub.verify_token`, and returns `hub.challenge`.
- **POST Receiver**: Listens for `"hi"` or `"hello"` greetings and automatically invokes `send_flow_message(to)` to dispatch the Flow card to the user's WhatsApp.

---

### D. Meta Flow JSON (`wa_flow/flow_definitions/flow.json`)
- Fixed all input and button labels to strictly satisfy Meta's **<= 20 character length constraint** (eliminating the red preview error):
  - `Phone Number` (12 chars)
  - `Delivery Address` (16 chars)
  - `Full Name` (9 chars)
  - `Payment Method` (14 chars)
  - `Review Summary` (14 chars)
  - `Confirm Order` (13 chars)
- Uploaded and validated with **0 validation errors** on Meta.

---

## 2. Active Meta Assets & Configuration

| Configuration | Value |
|---|---|
| **App ID** | `1872326637482499` (farm) |
| **WABA ID** | `1965689270778996` |
| **Phone Number ID** | `1297443690119359` (`+1 555-649-0799`) |
| **Current Flow ID (API)** | `1604466031315962` |
| **Original Flow ID** | `1081930417655056` |
| **Flow Status on Meta** | `DRAFT` (Validation Errors: 0) |
| **Endpoint URI** | `https://upon-washday-aerobics.ngrok-free.dev/whatsapp/flow/` |
| **Public Key** | Uploaded to Meta via RSA 2048-bit PEM |
| **Private Key** | `whatsapp_flow_private.pem` (Local workspace) |

---

## 3. Test Verification Results

All unit tests run and pass:
```bash
python manage.py test wa_flow
```
```text
Ran 7 tests in 0.330s

OK
```

Standard text messages and interactive button messages sent via Cloud API deliver with **HTTP 200 OK** directly to WhatsApp.

---

## 4. Key Details for Tomorrow's Discussion

When discussing the Meta account status tomorrow, here is the exact technical detail:

1. **Backend & Codebase**:
   - The Django implementation, data models, encryption, and Flow contracts are **100% complete and working**.
2. **Meta Integrity Requirement (`Error 139000`)**:
   - Meta Cloud API allows text and button messages from this test account (`HTTP 200 OK`).
   - However, Meta enforces an automated integrity block on `type: flow` until:
     - **Business Info** is saved in [Meta Business Suite > Business Info](https://business.facebook.com/settings/info) (Legal Name, Country, Website).
     - A **Payment Method** is added in [Meta Business Settings > Payment Methods](https://business.facebook.com/settings/payment-methods).
3. **Alternative Access**:
   - The live web preview with real-time backend data exchange can be tested at:
     `http://127.0.0.1:8000/order/`
