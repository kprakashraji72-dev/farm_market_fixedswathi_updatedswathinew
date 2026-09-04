"""
Forms used by the Admin Dashboard's Inventory management pages
(Module: Dashboard). Kept in the inventory app since they operate on
inventory models.
"""
from django import forms
from .models import Farm, Product, Category, ProductVariant


class FarmForm(forms.ModelForm):
    class Meta:
        model = Farm
        fields = ['owner', 'name', 'description', 'location', 'cover_image', 'video_url', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if not isinstance(field.widget, (forms.CheckboxInput,)):
                field.widget.attrs.update({'class': 'form-control'})


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['farm', 'category', 'name', 'description', 'price', 'unit', 'stock_quantity', 'image', 'is_active']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if not isinstance(field.widget, (forms.CheckboxInput,)):
                field.widget.attrs.update({'class': 'form-control'})


class FarmerFarmProfileForm(forms.ModelForm):
    """Self-service farm profile form for a farmer partner — no 'owner' field,
    the view sets that from request.user, and no 'is_active' switch (admin controls that)."""

    class Meta:
        model = Farm
        fields = ['name', 'description', 'location', 'cover_image', 'video_url']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})


class FarmerProductForm(forms.ModelForm):
    """Self-service product form for a farmer partner — the farm is fixed to
    their own farm by the view, so it's not exposed here.

    Farmers do NOT set the customer-facing price directly (that field is
    reserved for the admin — see dashboard.views.product_toggle_approved).
    Instead they quote what they're charging (often a bulk/wholesale lot
    price, e.g. "1 for 22 pieces") via cost_price + bulk_quantity, and an
    admin turns that into a priced, marked-up retail listing on approval.
    """

    class Meta:
        model = Product
        fields = ['category', 'name', 'description', 'cost_price', 'bulk_quantity', 'unit', 'stock_quantity', 'image', 'is_active']
        labels = {
            'cost_price': 'Your price (₹)',
            'bulk_quantity': 'For how many units?',
        }
        help_texts = {
            'cost_price': 'What you charge for the quantity below — e.g. 1 for a bulk lot of 22 pieces.',
            'bulk_quantity': 'Number of units that price covers. Use 1 if it\u2019s already a per-unit price.',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cost_price'].required = True
        for name, field in self.fields.items():
            if not isinstance(field.widget, (forms.CheckboxInput,)):
                field.widget.attrs.update({'class': 'form-control'})


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'icon']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})


class ProductVariantForm(forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = ['label', 'price', 'stock_quantity', 'sort_order', 'is_active']
        widgets = {
            'label': forms.TextInput(attrs={'placeholder': 'e.g. 400g, 1kg, 2kg'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if not isinstance(field.widget, (forms.CheckboxInput,)):
                field.widget.attrs.update({'class': 'form-control'})
