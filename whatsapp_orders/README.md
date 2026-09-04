# WhatsApp Orders — Interactive WhatsApp Flow Backend

A production-ready Django REST backend powering the WhatsApp Cloud API Flow ordering experience for Farm Fresh Produce.

---

## Table of Contents
1. [Overview](#overview)
2. [Architecture & Endpoints](#architecture--endpoints)
3. [Local Draft Testing Guide](#local-draft-testing)
   - [Step 1: Run Migrations & Seed Products](#1-run-migrations--seed-products)
   - [Step 2: Start Django & ngrok](#2-start-django--ngrok)
   - [Step 3: Wire Endpoint URI in WhatsApp Manager](#3-wire-endpoint-uri-in-whatsapp-manager)
   - [Step 4: Verify Endpoint Health](#4-verify-endpoint-health)
   - [Step 5: Test Screens in WhatsApp Manager Preview](#5-test-screens-in-whatsapp-manager-preview)
   - [Step 6: Console Log Verification Checklist](#6-console-log-verification-checklist)
4. [Pre-Publishing Production Checklist](#pre-publishing-production-checklist)
5. [Automated Test Suite](#automated-test-suite)

---

## Overview

When developing WhatsApp Flows, Meta restricts unpublished **Draft** flows from being dispatched via live Cloud API outbound messages (`/messages` endpoint returns `Error 139000 - Blocked By Integrity`). 

To solve this, the backend supports **Local Draft-Mode Testing** (`TESTING_MODE=true`):
- Incoming webhook triggers (`"hi"`, `"order"`, `"start"`) acknowledge with HTTP 200 and log draft mode status instead of invoking the Graph API.
- All screen transitions and cryptography are tested live and interactively using Meta's **"Preview Flow"** developer tool in WhatsApp Manager, routing requests directly to your local Django server over an ngrok tunnel.

---

## Architecture & Endpoints

| Method | Endpoint | Description | Encryption |
|---|---|---|---|
| `GET` | `/webhook/messages/` | Meta Webhook challenge handshake | None |
| `POST` | `/webhook/messages/` | Incoming customer messages (keyword trigger) | HMAC-SHA256 |
| `GET` | `/webhook/flow-data-exchange/health/` | Unencrypted health check for connectivity verification | None |
| `GET` | `/webhook/flow-data-exchange/` | Base endpoint status check | None |
| `POST` | `/webhook/flow-data-exchange/` | Meta Flow interactive lifecycle (`INIT`, `data_exchange`) | RSA-OAEP + AES-GCM |

---

## Local Draft Testing

Follow this step-by-step workflow to test the full 4-screen order flow locally:

### 1. Run Migrations & Seed Products

Ensure your database is initialized with the required schema and fresh farm catalog data:

```bash
# Activate virtual environment
# Windows: ..\venv\Scripts\activate
# Linux/macOS: source ../venv/bin/activate

# Apply migrations
python manage.py migrate

# Seed categories and products
python manage.py seed_products
```

Expected output:
```text
Seeding Categories & Products...
[Updated] Ooty Red Carrot (Rs.80.00/1 kg (or bunch))
[Updated] Fresh Orange Carrot (Rs.75.00/1 kg (or bunch))
[Updated] Regular Carrot (Rs.70.00/1 kg (or bunch))
[Updated] Organic Tomatoes (Rs.40.00/1 kg (or bunch))
...
Database seeding complete!
```

---

### 2. Start Django & ngrok

You can print guided instructions at any time using:
```bash
python manage.py runserver_ngrok
```

**Terminal 1 (Django):**
```bash
python manage.py runserver 8000
```

**Terminal 2 (ngrok tunnel):**
```bash
ngrok http 8000
```

Copy the forwarding HTTPS URL, e.g.:
`https://a1b2-c3d4.ngrok-free.app`

> **Note on Free ngrok URLs:**
> Free ngrok URLs change every time you restart ngrok. Remember to update the Endpoint URI in WhatsApp Manager whenever you restart your tunnel.

---

### 3. Wire Endpoint URI in WhatsApp Manager

1. Open [Meta Business Suite](https://business.facebook.com/) -> **WhatsApp Manager**.
2. Under **Account Tools**, click **Flows**.
3. Select your Flow: `Flow ID: 1422173683118152` (or your configured `WHATSAPP_FLOW_ID`).
4. Click the **Endpoint** tab (or **Flow Settings** -> **Endpoint**).
5. Paste your full ngrok endpoint URL:
   ```text
   https://<your-ngrok-subdomain>.ngrok-free.app/webhook/flow-data-exchange/
   ```
6. Ensure your public key (`whatsapp_flow_public.pem`) is uploaded under **Flow Settings** -> **Public Key**.
7. Click **Save** or **Validate Endpoint**.

---

### 4. Verify Endpoint Health

Before opening the Flow Preview, verify that Meta and your browser can reach your local Django backend through ngrok:

```bash
curl https://<your-ngrok-subdomain>.ngrok-free.app/webhook/flow-data-exchange/health/
```

Expected response (`HTTP 200`):
```json
{
  "status": "ok",
  "service": "whatsapp_flow_data_exchange",
  "testing_mode": true,
  "timestamp": "2026-09-04T06:30:00.000000Z"
}
```

---

### 5. Test Screens in WhatsApp Manager Preview

Inside WhatsApp Manager's Flow Builder, click **Preview Flow** (or **Test on WhatsApp**):

1. **Screen 1: PRODUCTS (`INIT`)**
   - Flow opens with default category `🥕 Fresh Vegetables`.
   - Change Category to `🍎 Farm Fresh Fruits`: observe instant dynamic product list reload.
   - Change Product to `Robusta Banana`: observe price update (`₹ 50.00/kg`).
   - Change Quantity to `2 kg`: observe subtotal updating (`₹ 100.00` + `₹ 5.00` delivery = `₹ 105.00`).
   - Click **Continue to Delivery**.

2. **Screen 2: DELIVERY (`DELIVERY`)**
   - Displays selected product recap and pricing.
   - Enter Customer Name (e.g., `Prakash Raji`).
   - Enter Delivery Phone (e.g., `918807856058`).
   - Enter Delivery Address (e.g., `123 Green Valley Road`).
   - Select Payment Method: `Cash on Delivery (COD)` or `UPI on Delivery`.
   - Click **Review Order**.

3. **Screen 3: SUMMARY (`SUMMARY`)**
   - Displays complete order recap with name, delivery address, phone, item, and total amount.
   - Click **Confirm & Place Order**.

4. **Screen 4: COMPLETE (`COMPLETE`)**
   - Displays success message and assigned Order ID (e.g., `ORD-1`).
   - An `Order` record is created in the database and confirmation task is dispatched.

---

### 6. Console Log Verification Checklist

With `DEBUG=True` and `TESTING_MODE=true`, the Django console displays verbose logs for every transition:

- **When "hi" message received at webhook:**
  ```text
  [Webhook] Trigger keyword matched from +918807856058: 'hi'
  [INFO] Draft mode active — trigger flow manually via Preview in WhatsApp Manager
  ```
  *(Confirms no Graph API call was made, preventing Error 139000).*

- **When opening Flow (INIT):**
  ```text
  ==================== [FLOW INCOMING DECRYPTED PAYLOAD] ====================
  Action: INIT | Screen:  | Trigger: None | Flow Token: flow_...
  ==================== [FLOW OUTGOING RESPONSE (PRE-ENCRYPTION)] ============
  Target Screen: PRODUCTS
  ```

- **When changing Category / Product / Quantity:**
  ```text
  ==================== [FLOW INCOMING DECRYPTED PAYLOAD] ====================
  Action: data_exchange | Screen: PRODUCTS | Trigger: category_selected
  Form Data: { "category": "cat_fruits", "product": "prod_apple", "quantity": "qty_1" }
  ```

- **When submitting Order:**
  ```text
  [FlowDataExchange] Order #1 created/resolved for +918807856058
  [FlowDataExchange] Enqueued Celery send_confirmation_task for Order #1
  Target Screen: COMPLETE
  ```

---

## Pre-Publishing Production Checklist

Before publishing the Flow for public use, perform the following checklist:

- [ ] **1. Disable Testing Mode:**
  In `.env`, set:
  ```dotenv
  TESTING_MODE=false
  WHATSAPP_FLOW_MODE=published
  ```
- [ ] **2. Set Permanent Production HTTPS Domain:**
  Replace temporary ngrok URL with your production domain (e.g., `https://api.yourdomain.com/webhook/flow-data-exchange/`) in WhatsApp Manager -> Flow Settings -> Endpoint.
- [ ] **3. Validate Flow JSON:**
  In Meta Flow Builder, click **Validate** and ensure there are 0 errors or warnings.
- [ ] **4. Publish Flow:**
  In Meta Flow Builder, click **Publish**. Once published, the flow status becomes `PUBLISHED`.
- [ ] **5. Live Customer Trigger Test:**
  Send `"hi"` from a personal WhatsApp account to your WhatsApp Business Number. Confirm that the interactive Flow trigger message arrives in chat and can be opened normally.

---

## Automated Test Suite

Run the full end-to-end test suite anytime:

```bash
python test_backend_suite.py
```

Validates:
- Meta webhook handshake verification
- Keyword trigger handling under `TESTING_MODE`
- Unencrypted health check endpoint
- Screen transitions (`INIT`, `category_selected`, `product_selected`, `DELIVERY`, `SUMMARY`, `COMPLETE`)
- Cryptographic round-trip (RSA-OAEP + AES-GCM)
- Celery cleanup tasks
