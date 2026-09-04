import django, os, json
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'farm_market.settings')
django.setup()

from django.test import RequestFactory
from django.contrib.sessions.backends.db import SessionStore
from store.views import chat_message_view

rf = RequestFactory()

# 1. Test adding all products
req_all = rf.post('/chat/message/', data=json.dumps({'message': 'Add all products to my cart'}), content_type='application/json')
req_all.user = type('U', (), {'is_authenticated': False, 'first_name': '', 'username': 'Guest'})()
req_all.session = SessionStore()
resp_all = chat_message_view(req_all)
data_all = json.loads(resp_all.content)
print('Add all products status:', resp_all.status_code)
print('Add all cart count:', data_all.get('cart_count'))

# 2. Test individual products from DB
for item_name in ['apple', 'beetroot', 'cherry tomato', 'prakash']:
    req_item = rf.post('/chat/message/', data=json.dumps({'message': f'Add 2 {item_name} to cart'}), content_type='application/json')
    req_item.user = type('U', (), {'is_authenticated': False, 'first_name': '', 'username': 'Guest'})()
    req_item.session = SessionStore()
    resp_item = chat_message_view(req_item)
    data_item = json.loads(resp_item.content)
    print(f'Item "{item_name}": cart_count={data_item.get("cart_count")}, added={data_item.get("added_item", {}).get("name")}')
