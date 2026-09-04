from decimal import Decimal
import re
from django.db.models import Q
from .models import Product, Category, LIVE_APPROVED_PRODUCT_Q


def compute_relevance(product_name: str, category_name: str, description: str, query: str) -> int:
    """
    Computes a relevance score (0-100) based on how closely the product matches
    the customer's search query.
    """
    p_name = product_name.lower().strip()
    q = query.lower().strip()
    cat_name = (category_name or '').lower().strip()
    desc = (description or '').lower().strip()

    # Exact name match
    if p_name == q:
        return 100

    # Name starts with query or contains query as a distinct word (e.g. "Ooty Carrot", "Baby Carrot")
    tokens = re.findall(r'\w+', p_name)
    q_tokens = re.findall(r'\w+', q)

    if p_name.startswith(q) or any(t == q for t in tokens):
        return 85

    # All query words present in product name
    if all(qt in p_name for qt in q_tokens if len(qt) > 1):
        return 75

    # Partial substring in name (e.g. "carr" in "carrot")
    if q in p_name:
        return 60

    # Match in category name
    if q in cat_name or any(t == q for t in re.findall(r'\w+', cat_name)):
        return 35

    # Match in product description
    if q in desc:
        return 20

    return 0


def get_search_recommendations(query: str, category_slug: str = None):
    """
    Executes smart recommendation ranking for a given search query:
    1. Direct & variety matches sorted by Relevance -> Price -> Rating.
    2. Identifies and flags the true lowest price product.
    3. Finds complementary 'You May Also Like' produce.
    """
    clean_query = (query or '').strip()
    base_qs = Product.objects.filter(LIVE_APPROVED_PRODUCT_Q, is_active=True).select_related('farm', 'category')

    if category_slug:
        base_qs = base_qs.filter(category__slug=category_slug)

    if not clean_query:
        # Non-search regular catalog listing
        return {
            'has_query': False,
            'query': '',
            'primary_matches': [],
            'lowest_price_item': None,
            'related_products': [],
            'total_matches': 0,
        }

    # Step 1: Candidate retrieval
    # Look for products matching query in name, category, or description
    q_filter = (
        Q(name__icontains=clean_query) |
        Q(category__name__icontains=clean_query) |
        Q(description__icontains=clean_query)
    )
    candidate_products = list(base_qs.filter(q_filter))

    # Score and decorate candidates
    scored_products = []
    for p in candidate_products:
        cat_name = p.category.name if p.category else ''
        score = compute_relevance(p.name, cat_name, p.description, clean_query)
        if score > 0:
            p.relevance_score = score
            
            # Enrich with realistic retail strike-through price and discount percent
            effective_price = Decimal(str(p.display_price))
            # Generate consistent reference original price (15% to 30% higher)
            multiplier = Decimal('1.20') + (Decimal(str((p.id % 4) * 5)) / Decimal('100'))
            p.original_price = round(effective_price * multiplier, 2)
            if p.original_price > effective_price:
                p.discount_percent = int(round(((p.original_price - effective_price) / p.original_price) * 100))
            else:
                p.discount_percent = 0
                
            # Consistent farm rating
            p.rating_score = round(4.5 + ((p.id % 5) * 0.1), 1)
            p.review_count = 12 + ((p.id * 7) % 35)
            p.is_lowest_price = False
            
            scored_products.append(p)

    # Sort primarily by relevance (highest first), then price (lowest first)
    scored_products.sort(key=lambda x: (-x.relevance_score, x.display_price, -x.stock_quantity))

    # Step 2: Identify the single true lowest-price product among search matches
    lowest_price_item = None
    if scored_products:
        # Find the product with minimum display price in the matching set
        min_price_item = min(scored_products, key=lambda x: x.display_price)
        min_price_item.is_lowest_price = True
        lowest_price_item = min_price_item

    # Step 3: Find complementary 'You May Also Like' products
    # Get categories of the matched products or general category
    matched_ids = [p.id for p in scored_products]
    matched_categories = list(set([p.category_id for p in scored_products if p.category_id]))

    related_qs = Product.objects.filter(
        LIVE_APPROVED_PRODUCT_Q,
        is_active=True
    ).exclude(id__in=matched_ids).select_related('farm', 'category')

    if matched_categories:
        related_products = list(related_qs.filter(category_id__in=matched_categories)[:6])
    else:
        related_products = list(related_qs[:6])

    # Decorate related products with price info
    for rp in related_products:
        eff_price = Decimal(str(rp.display_price))
        rp.original_price = round(eff_price * Decimal('1.20'), 2)
        rp.discount_percent = int(round(((rp.original_price - eff_price) / rp.original_price) * 100))
        rp.rating_score = round(4.6 + ((rp.id % 4) * 0.1), 1)
        rp.review_count = 15 + ((rp.id * 5) % 25)

    return {
        'has_query': True,
        'query': clean_query,
        'primary_matches': scored_products,
        'lowest_price_item': lowest_price_item,
        'related_products': related_products,
        'total_matches': len(scored_products),
    }
