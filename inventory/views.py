"""
Customer-facing catalog views: product listing with search/category filter,
product detail, and the farm detail page (info + gallery + video).

A product/farm is only shown to customers when it's marked active AND,
if it belongs to a farmer partner, that farmer has been admin-verified.
Farms with no owner (e.g. admin-managed demo data) are always visible.
See inventory.models.LIVE_FARM_Q for the shared filter.
"""
from django.core.paginator import Paginator
from django.shortcuts import render, get_object_or_404
from orders.cart import Cart, product_key, variant_key
from .models import Product, Category, Farm, LIVE_FARM_Q, LIVE_APPROVED_PRODUCT_Q
from .recommendations import get_search_recommendations


def product_list_view(request):
    """
    Produce catalog view with intelligent search recommendations, variety grouping,
    lowest-price highlighting, and category filtering.
    """
    query = request.GET.get('q', '').strip()
    category_slug = request.GET.get('category', '').strip()
    categories = Category.objects.all()

    if query:
        # Execute smart search & recommendation engine
        rec_data = get_search_recommendations(query=query, category_slug=category_slug)
        primary_matches = rec_data['primary_matches']

        paginator = Paginator(primary_matches, 16)
        page_obj = paginator.get_page(request.GET.get('page'))

        context = {
            'is_search_view': True,
            'query': query,
            'selected_category': category_slug,
            'categories': categories,
            'page_obj': page_obj,
            'recommendations': rec_data,
            'lowest_price_item': rec_data['lowest_price_item'],
            'related_products': rec_data['related_products'],
            'total_matches': rec_data['total_matches'],
        }
    else:
        # Standard catalog browsing
        products = Product.objects.filter(LIVE_APPROVED_PRODUCT_Q, is_active=True).select_related('farm', 'category')
        if category_slug:
            products = products.filter(category__slug=category_slug)

        paginator = Paginator(products, 12)
        page_obj = paginator.get_page(request.GET.get('page'))

        context = {
            'is_search_view': False,
            'query': '',
            'selected_category': category_slug,
            'categories': categories,
            'page_obj': page_obj,
            'recommendations': None,
            'lowest_price_item': None,
            'related_products': [],
            'total_matches': products.count(),
        }

    return render(request, 'store/product_list.html', context)


def product_detail_view(request, slug):
    product = get_object_or_404(
        Product.objects.filter(LIVE_APPROVED_PRODUCT_Q).select_related('farm', 'category'), slug=slug, is_active=True
    )
    related_products = Product.objects.filter(
        LIVE_APPROVED_PRODUCT_Q, category=product.category, is_active=True
    ).exclude(pk=product.pk)[:4]

    cart = Cart(request)

    if product.has_variants:
        variants = []
        for variant in product.variants.filter(is_active=True):
            in_cart_qty = cart.cart.get(variant_key(variant.id), 0)
            variants.append({
                'variant': variant,
                'in_cart_qty': in_cart_qty,
                'remaining_stock': max(0, variant.stock_quantity - in_cart_qty),
            })
        return render(request, 'store/product_detail.html', {
            'product': product,
            'related_products': related_products,
            'variants': variants,
        })

    in_cart_qty = cart.cart.get(product_key(product.id), 0)
    remaining_stock = max(0, product.stock_quantity - in_cart_qty)

    return render(request, 'store/product_detail.html', {
        'product': product,
        'related_products': related_products,
        'in_cart_qty': in_cart_qty,
        'remaining_stock': remaining_stock,
    })


def farm_detail_view(request, slug):
    farm = get_object_or_404(Farm.objects.filter(LIVE_FARM_Q), slug=slug, is_active=True)
    products = farm.products.filter(is_active=True, is_approved=True).select_related('category')
    farm_categories = Category.objects.filter(products__in=products).distinct()
    return render(request, 'store/farm_detail.html', {
        'farm': farm,
        'products': products,
        'farm_categories': farm_categories,
    })
