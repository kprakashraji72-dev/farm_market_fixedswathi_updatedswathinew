# WhatsApp Cloud API Flow Backend (`wa_flow`)

Production-ready Django backend implementing an interactive WhatsApp Cloud API **Flow** ordering experience for Farm Fresh Produce.

When a customer messages **"hi"** or **"hello"** to your WhatsApp Business number, the backend sends an interactive Flow trigger message that launches a 4-screen in-app Flow:
`PRODUCTS` ➔ `DELIVERY` ➔ `SUMMARY` ➔ `COMPLETE`

---

## Architecture Overview

```text
               +-------------------------------------------+
               |             WhatsApp Client               |
               +--------------------+----------------------+
                                    |
                    1. "hi" / "hello" webhook event
                                    v
     +-------------------------------------------------------------+
     | GET /webhook/          -> Webhook verification handshake     |
     | POST /webhook/         -> Sends interactive Flow message    |
     +------------------------------+------------------------------+
                                    |
                 2. Opens Flow & triggers Data-Exchange
                                    v
     +-------------------------------------------------------------+
     | POST /flow-endpoint/   -> Decrypts RSA-OAEP + AES-128-GCM   |
     |                           Dispatches screens (PRODUCTS...)  |
     |                           Encrypts response with inverted IV|
     +-------------------------------------------------------------+
```

- **`wa_flow/views.py`**: Thin views for `/webhook/` and `/flow-endpoint/` (`csrf_exempt`).
- **`wa_flow/services.py`**: `send_flow_message()`, `handle_flow_action()`, and `create_order()`.
- **`wa_flow/flow_crypto.py`**: WhatsApp Flows cryptographic engine (RSA-OAEP SHA-256 + AES-128-GCM with inverted IV).
- **`wa_flow/flow_definitions/flow.json`**: Meta Flow JSON v5.0 / data_api_version 3.0 definition.

---

## 1. Generating the RSA Key Pair

WhatsApp Flows requires an RSA 2048-bit key pair to exchange encrypted AES symmetric keys:

```bash
# 1. Generate a private RSA key (2048 bit)
openssl genrsa -out whatsapp_flow_private.pem 2048

# 2. Extract the public key in PEM format
openssl rsa -in whatsapp_flow_private.pem -pubout -out whatsapp_flow_public.pem
```

- **Public Key (`whatsapp_flow_public.pem`)**: Uploaded to Meta Flow Builder (under **Flow Settings** ➔ **Public Key**).
- **Private Key (`whatsapp_flow_private.pem`)**: Stored securely on your server and referenced in your `.env`.

---

## 2. Environment Configuration (`.env`)

Configure the following variables in your `.env`:

```dotenv
# Meta WhatsApp Cloud API credentials
WHATSAPP_TOKEN=EAAM...your_access_token...
PHONE_NUMBER_ID=1297443690119359
FLOW_ID=1081930417655056

# Webhook Verification Token (choose any secure random string)
VERIFY_TOKEN=fresh_trace_wa_c5a23fd481477ef350e8944373ddfe3a

# Flow Private Key (path or PEM content)
FLOW_PRIVATE_KEY_PATH=whatsapp_flow_private.pem
FLOW_PRIVATE_KEY_PEM=
FLOW_PRIVATE_KEY_PASSPHRASE=
FLOW_MODE=draft
```

---

## 3. Creating & Configuring the Flow in Meta Flow Builder

1. Navigate to **Meta WhatsApp Manager** ➔ **Flows** ➔ **Create Flow**.
2. Set Flow Name (e.g., `farm_produce_flow`) and Category to **Customer Support** or **Order Management**.
3. In the Flow Builder:
   - Click the **`...`** (Options menu) ➔ **Import JSON**.
   - Select and import `wa_flow/flow_definitions/flow.json`.
4. Click **Settings** (Gear icon ⚙️):
   - **Endpoint URI**: Paste your public HTTPS endpoint:
     ```text
     https://<YOUR-DOMAIN-OR-NGROK>/flow-endpoint/
     ```
   - **Public Key**: Copy and paste the contents of `whatsapp_flow_public.pem`.
   - Click **Save**.
5. Test the endpoint connection:
   - Click the **Actions** / **Test Endpoint** button.
   - You should see a green checkmark confirming `status: active`!

---

## 4. Configuring the WhatsApp Webhook in Meta Developer Portal

1. Go to your **[Meta Developer Portal](https://developers.facebook.com/)** ➔ Your App ➔ **WhatsApp** ➔ **Configuration**.
2. Under **Webhook**:
   - Click **Edit**.
   - **Callback URL**: `https://<YOUR-DOMAIN-OR-NGROK>/webhook/`
   - **Verify Token**: Must match your `VERIFY_TOKEN` from `.env`.
   - Click **Verify and Save**.
3. Under **Webhook Fields**, subscribe to **`messages`**.

---

## 5. Local Testing with Ngrok & Runserver

### Step A: Start the Django Server
```bash
python manage.py runserver 8000
```

### Step B: Start Ngrok Tunnel
In a second terminal window:
```bash
ngrok http 8000
```
Copy the generated public forwarding URL (e.g., `https://upon-washday-aerobics.ngrok-free.dev`).

Update both URLs in Meta:
- **WhatsApp Webhook URL**: `https://upon-washday-aerobics.ngrok-free.dev/webhook/`
- **Flow Endpoint URL**: `https://upon-washday-aerobics.ngrok-free.dev/flow-endpoint/`

### Step C: Test via WhatsApp
1. Open WhatsApp on your phone and send **`hi`** or **`hello`** to your WhatsApp Business number.
2. You will instantly receive the interactive **Farm Fresh Produce** card with an **`Order Produce 🛒`** button.
3. Tap **`Order Produce 🛒`**:
   - **Screen 1 (`PRODUCTS`)**: Select produce category (Fresh Vegetables, Fruits, Greens) & enter quantity.
   - **Screen 2 (`DELIVERY`)**: Enter street address and pick preferred delivery date.
   - **Screen 3 (`SUMMARY`)**: Review order recap.
   - **Screen 4 (`COMPLETE`)**: Order is created via `create_order(data)` and confirmed with a unique order ID (`ORD-XXXXX`)!

---

## 6. Running Unit Tests

Run the automated test suite covering webhook handshakes, flow cryptography, and screen navigation:

```bash
python manage.py test wa_flow
```
Output:
```text
Ran 7 tests in 0.45s - OK
```
