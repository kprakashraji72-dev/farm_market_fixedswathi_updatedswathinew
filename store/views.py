from django.shortcuts import render
from inventory.models import Product, Category, Farm, LIVE_FARM_Q, LIVE_APPROVED_PRODUCT_Q
import json
import re
import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from orders.cart import Cart, product_key, variant_key
from orders.models import Order


def home_view(request):
    """Customer storefront home: featured products, categories, and farms."""
    context = {
        'featured_products': Product.objects.filter(LIVE_APPROVED_PRODUCT_Q, is_active=True).select_related('farm')[:8],
        'categories': Category.objects.all()[:8],
        'farms': Farm.objects.filter(LIVE_FARM_Q, is_active=True)[:6],
    }
    return render(request, 'store/home.html', context)


def portals_view(request):
    """
    The 'app switcher' hub — like Flipkart/Instamart's separate portals
    for buyers, sellers, and delivery partners. Shows one card per role
    (Customer / Farmer Partner / Delivery Partner / Admin) linking to
    that role's own login & signup pages.
    """
    return render(request, 'store/portals.html')


def error_404(request, exception):
    return render(request, 'errors/404.html', status=404)


def error_500(request):
    return render(request, 'errors/500.html', status=500)


@require_POST
def chat_message_view(request):
    """
    Handles customer chat messages against OpenRouter
    Provides system context including matched active products, recent customer orders,
    and supports executing AI-driven Add to Cart actions directly into the session cart.
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        user_message = data.get('message', '').strip()
    except Exception:
        return JsonResponse({'error': 'Invalid JSON request payload.'}, status=400)

    if not user_message:
        return JsonResponse({'error': 'Message cannot be empty.'}, status=400)

    if len(user_message) > 500:
        return JsonResponse({'error': 'Message exceeds 500 characters limit.'}, status=400)

    hf_token = getattr(settings, 'HF_API_TOKEN', '')
    if not hf_token:
        return JsonResponse({
            'reply': 'The AI assistant is not configured yet. Please ask the site administrator to configure OPENROUTER_API_KEY / HF_API_TOKEN in settings or .env file.'
        })

    user_lower = user_message.lower()

    # Load all live, approved products from the database
    all_db_products = list(
        Product.objects.filter(LIVE_APPROVED_PRODUCT_Q, is_active=True)
        .select_related('farm', 'category')
    )

    # -------------------------------------------------------------
    # 1. Direct handling to add ALL products from the database to cart
    # -------------------------------------------------------------
    if any(phrase in user_lower for phrase in ['add all', 'all product', 'add everything', 'all items', 'add all to cart', 'buy all']):
        cart = Cart(request)
        added_count = 0
        for p in all_db_products:
            if p.stock_quantity > 0:
                if p.has_variants:
                    v = p.variants.filter(is_active=True).first()
                    if v:
                        cart.add(variant_key(v.id), quantity=1)
                    else:
                        cart.add(product_key(p.id), quantity=1)
                else:
                    cart.add(product_key(p.id), quantity=1)
                added_count += 1

        reply = (
            f"🛒 **Added all {added_count} products from the database to your cart!**\n\n"
            f"Your shopping cart now has **{len(cart)} total items**. You can proceed to checkout or continue shopping!"
        )

        history = request.session.get('chat_history', [])
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": reply})
        request.session['chat_history'] = history[-16:]
        if hasattr(request.session, 'modified'):
            request.session.modified = True

        return JsonResponse({
            'reply': reply,
            'cart_count': len(cart),
            'added_item': {
                'name': f'All {added_count} Database Products',
                'quantity': added_count,
                'cart_count': len(cart),
            },
        })

    # Search products using keyword matching on name, description, and category across entire DB
    words = [w for w in re.findall(r'\w+', user_lower) if len(w) > 1]
    matched_products = []
    if words:
        for p in all_db_products:
            p_text = f"{p.name} {p.description or ''} {p.category.name if p.category else ''} {p.farm.name if p.farm else ''}".lower()
            if any(w in p_text for w in words):
                matched_products.append(p)

    if not matched_products:
        matched_products = all_db_products[:8]

    # Fetch customer's last 5 orders if logged in
    recent_orders = []
    if request.user.is_authenticated and getattr(request.user, 'is_customer_role', False):
        recent_orders = list(
            Order.objects.filter(customer=request.user)
            .order_by('-created_at')[:5]
        )

    # Build system context with database products
    products_context = []
    for p in (matched_products if len(matched_products) >= 6 else all_db_products[:12]):
        farm_name = p.farm.name if p.farm else "Direct Farm"
        stock_str = f"{p.stock_quantity} {p.unit} in stock" if p.stock_quantity > 0 else "Out of stock"
        products_context.append(f"- {p.name} [item_ref:{p.id}]: ₹{p.price}/{p.unit} ({stock_str}, Farm: {farm_name})")

    orders_context = []
    for o in recent_orders:
        eta_str = o.estimated_delivery_time.strftime('%b %d, %Y %I:%M %p') if o.estimated_delivery_time else 'Calculating'
        orders_context.append(f"- Order #{o.id}: Status '{o.get_status_display()}', Amount ₹{o.total_amount}, ETA: {eta_str}")

    user_note = ""
    if not request.user.is_authenticated:
        user_note = "Note: The user is currently browsing as a guest. If they ask about their personal order, ask them to log in to view their order status."

    system_prompt = (
        "You are Fresh Trace's intelligent and friendly AI shopping assistant.\n"
        "Help the customer with product information, prices, farm provenance, and their recent orders.\n\n"
        "RELEVANT STORE PRODUCTS:\n" + ("\n".join(products_context) if products_context else "No matching products found.") + "\n\n"
        "CUSTOMER'S RECENT ORDERS:\n" + ("\n".join(orders_context) if orders_context else "No recent orders on file.") + "\n\n"
        + (user_note + "\n\n" if user_note else "")
        + "SPECIAL CAPABILITY — ADD TO CART:\n"
        "If the customer asks to add an item to their cart or buy produce (e.g. 'add 2 carrots to cart', 'buy 1 kg apples', 'add tomato', 'add all products'):\n"
        "1. Identify the matching item_ref number from the products list above.\n"
        "2. Include the action tag in your response: [ACTION:ADD_TO_CART:{\"product_id\": <item_ref_number>, \"quantity\": <qty>}]\n"
        "3. Accompany it with a cheerful confirmation that the item and quantity have been added to their cart with total price details!\n\n"
        "IMPORTANT PRESENTATION RULES:\n"
        "1. NEVER output raw tool tokens or tags like <|tool_call_start|>, <|tool_call_end|>, or [ACTION...]. Always write natural, friendly English to the customer.\n"
        "2. NEVER mention or show raw product IDs, item_ref numbers, or database keys to the customer. Only use clean product names (e.g. 'Fresh Organic Carrots'), prices, and farm names.\n"
        "3. Give concise, warm, helpful, and natural responses.\n"
        "4. Only quote prices, stocks, and order statuses based strictly on the context provided above.\n"
        "5. If asking about delivery, refer to their specific recent order ETA if available."
    )

    history = request.session.get('chat_history', [])
    messages_payload = [{"role": "system", "content": system_prompt}]
    for turn in history[-16:]:
        messages_payload.append({"role": turn.get("role"), "content": turn.get("content")})
    messages_payload.append({"role": "user", "content": user_message})

    model_id = getattr(settings, 'HF_CHAT_MODEL', 'liquid/lfm-2.5-2.6b:free')

    is_openrouter = hf_token.startswith('sk-or-')
    if is_openrouter:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {hf_token}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://127.0.0.1:8000",
            "X-Title": "Fresh Trace",
        }
        payload = {
            "model": model_id,
            "messages": messages_payload,
            "max_tokens": 300,
            "temperature": 0.7,
        }
    else:
        url = f"https://api-inference.huggingface.co/models/{model_id}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {hf_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_id,
            "messages": messages_payload,
            "max_tokens": 300,
            "temperature": 0.7,
        }

    reply = None
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code == 200:
            resp_json = resp.json()
            reply = resp_json.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
        elif is_openrouter:
            payload["model"] = "liquid/lfm-2.5-2.6b:free"
            resp_alt = requests.post(url, headers=headers, json=payload, timeout=15)
            if resp_alt.status_code == 200:
                resp_json = resp_alt.json()
                reply = resp_json.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
        else:
            fallback_url = f"https://api-inference.huggingface.co/models/{model_id}"
            formatted_prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
            for turn in history[-8:]:
                formatted_prompt += f"<|im_start|>{turn.get('role')}\n{turn.get('content')}<|im_end|>\n"
            formatted_prompt += f"<|im_start|>user\n{user_message}<|im_end|>\n<|im_start|>assistant\n"

            resp2 = requests.post(fallback_url, headers=headers, json={"inputs": formatted_prompt, "parameters": {"max_new_tokens": 250, "return_full_text": False}}, timeout=15)
            if resp2.status_code == 200:
                resp2_json = resp2.json()
                if isinstance(resp2_json, list) and len(resp2_json) > 0:
                    reply = resp2_json[0].get('generated_text', '').strip()
                elif isinstance(resp2_json, dict) and 'generated_text' in resp2_json:
                    reply = resp2_json.get('generated_text', '').strip()
    except requests.exceptions.Timeout:
        reply = "The request timed out. Please try asking again with a shorter message."
    except Exception:
        reply = "I'm having a little trouble connecting right now. Please try again in a moment."

    if not reply:
        if any(w in user_lower for w in ['vegetable', 'fruit', 'produce', 'available', 'items', 'list', 'what do you have', 'organic', 'crop', 'carrot', 'spinach', 'tomato', 'fresh', 'all']):
            prods = matched_products[:6] if matched_products else all_db_products[:6]
            lines = [f"- **{p.name}**: ₹{p.price}/{p.unit} ({'In stock' if p.stock_quantity > 0 else 'Out of stock'}, Farm: *{p.farm.name if p.farm else 'Organic Partner Farm'}*)" for p in prods]
            reply = (
                f"🌱 **Here is what is freshly harvested & available in our organic store:**\n\n"
                + "\n".join(lines)
                + f"\n\nYou can say **'Add 2 {prods[0].unit if prods else 'kg'} of {prods[0].name if prods else 'Carrots'} to my cart'** or **'Add all products to cart'**!"
            )
        else:
            reply = "I'm here to help! Could you please repeat or rephrase your question about our fresh products or your orders?"

    # --- Process Add to Cart Intent ---
    added_item_info = None
    cart = Cart(request)
    product_to_add = None
    quantity_to_add = 1

    # 1. Check for JSON format: [ACTION:ADD_TO_CART:{"product_id": 31, "quantity": 1}]
    json_action_match = re.search(r'ADD_TO_CART[^\(\{]*[:\s]*(\{[^}]*\})', reply or '', re.DOTALL | re.IGNORECASE)
    if json_action_match:
        try:
            action_data = json.loads(json_action_match.group(1))
            pid = action_data.get('product_id')
            quantity_to_add = max(1, int(action_data.get('quantity', 1)))
            if pid:
                product_to_add = Product.objects.filter(LIVE_APPROVED_PRODUCT_Q, id=pid, is_active=True).first()
        except Exception:
            pass

    # 2. Check for tool-call / kwargs format: <|tool_call_start|>[ACTION[ADD_TO_CART](product_id='31', quantity=1)]<|tool_call_end|>
    if not product_to_add:
        call_action_match = re.search(r'ADD_TO_CART[^)]*?\(([^)]*)\)', reply or '', re.DOTALL | re.IGNORECASE)
        if call_action_match:
            try:
                args_str = call_action_match.group(1)
                p_m = re.search(r'product_id\s*=\s*[\'\"]?(\d+)[\'\"]?', args_str, re.IGNORECASE)
                q_m = re.search(r'quantity\s*=\s*[\'\"]?(\d+)[\'\"]?', args_str, re.IGNORECASE)
                pid = p_m.group(1) if p_m else None
                if q_m:
                    quantity_to_add = max(1, int(q_m.group(1)))
                if pid:
                    product_to_add = Product.objects.filter(LIVE_APPROVED_PRODUCT_Q, id=pid, is_active=True).first()
            except Exception:
                pass

    # 3. Fallback intent extraction across all database products if user clearly commanded to add to cart
    if not product_to_add and any(verb in user_lower for verb in ['add', 'buy', 'cart', 'put in cart', 'purchase']):
        best_match = None
        best_len = 0
        for p in all_db_products:
            p_name_l = p.name.lower()
            if p_name_l in user_lower and len(p_name_l) > best_len:
                best_match = p
                best_len = len(p_name_l)
            elif not best_match:
                words_in_name = [w for w in p_name_l.split() if len(w) > 2]
                if any(w in user_lower for w in words_in_name):
                    best_match = p

        product_to_add = best_match or (matched_products[0] if matched_products else None)
        qty_match = re.search(r'\b(\d+)\b', user_lower)
        if qty_match:
            try:
                quantity_to_add = max(1, int(qty_match.group(1)))
            except ValueError:
                quantity_to_add = 1

    # Strip action tags, tool-call tokens (<|...|>), and internal IDs from user reply
    if reply:
        reply = re.sub(r'<\|.*?\|>', '', reply, flags=re.DOTALL)
        reply = re.sub(r'\[ACTION\[[^\]]*\]\([^)]*\)\]', '', reply, flags=re.IGNORECASE | re.DOTALL)
        reply = re.sub(r'\[ACTION:ADD_TO_CART:?\s*\{.*?\}\s*\]', '', reply, flags=re.IGNORECASE | re.DOTALL)
        reply = re.sub(r'\[ACTION:ADD_TO_CART:?[^\]]*\]', '', reply, flags=re.IGNORECASE | re.DOTALL)
        reply = re.sub(r'\[?ADD_TO_CART\([^)]*\)\]?', '', reply, flags=re.IGNORECASE | re.DOTALL)
        reply = re.sub(r'\[ACTION.*?\]', '', reply, flags=re.IGNORECASE | re.DOTALL)
        reply = re.sub(r'\[\s*(PRODUCT_ID|item_ref|ID|Ref)\s*:\s*\d+\s*\]', '', reply, flags=re.IGNORECASE)
        reply = re.sub(r'\(\s*(Product\s*ID|item_ref|Ref|ID)\s*:\s*\d+\s*\)', '', reply, flags=re.IGNORECASE)
        reply = re.sub(r'\b(Product\s*ID|item_ref)\s*:\s*\d+\b', '', reply, flags=re.IGNORECASE)
        reply = reply.strip()

    if product_to_add:
        if product_to_add.has_variants:
            v = product_to_add.variants.filter(is_active=True).first()
            if v:
                cart.add(variant_key(v.id), quantity=quantity_to_add)
            else:
                cart.add(product_key(product_to_add.id), quantity=quantity_to_add)
        else:
            cart.add(product_key(product_to_add.id), quantity=quantity_to_add)

        added_item_info = {
            'product_id': product_to_add.id,
            'name': product_to_add.name,
            'quantity': quantity_to_add,
            'unit': product_to_add.unit,
            'price': str(product_to_add.price),
            'cart_count': len(cart),
        }

        # Ensure a cheerful confirmation is always given
        confirm_msg = f"🛒 Added {quantity_to_add} {product_to_add.unit} of **{product_to_add.name}** (₹{product_to_add.price}/{product_to_add.unit}) to your cart!"
        if not reply or 'cart' not in reply.lower():
            reply = f"{confirm_msg}\n\n{reply}".strip() if reply else confirm_msg

    if not reply:
        reply = "I'm here to help! Could you please let me know which product you would like to explore or add?"

    # Update session history capped to 16 items (8 turns)
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": reply})
    request.session['chat_history'] = history[-16:]
    if hasattr(request.session, 'modified'):
        request.session.modified = True

    return JsonResponse({
        'reply': reply,
        'cart_count': len(cart),
        'added_item': added_item_info,
    })


@require_POST
def chat_reset_view(request):
    """Clears the session-stored chat history."""
    if 'chat_history' in request.session:
        del request.session['chat_history']
        if hasattr(request.session, 'modified'):
            request.session.modified = True
    return JsonResponse({'status': 'cleared'})
