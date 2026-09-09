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
        if 'name' in self.fields:
            self.fields['name'].max_length = 100
            self.fields['name'].widget.attrs.update({
                'maxlength': '100',
                'placeholder': 'Official farm name (max 100 characters)',
            })
        for name, field in self.fields.items():
            if not isinstance(field.widget, (forms.CheckboxInput,)):
                field.widget.attrs.update({'class': 'form-control'})

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if len(name) > 100:
            raise forms.ValidationError('Farm name must not exceed 100 characters.')
        return name


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'farm', 'category', 'name', 'description', 'price', 'unit', 'stock_quantity',
            'harvest_date', 'received_date', 'image', 'is_active'
        ]
        labels = {
            'harvest_date': 'Harvest Date',
            'received_date': 'Received at Store Date',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'harvest_date': forms.DateInput(attrs={'type': 'date'}),
            'received_date': forms.DateInput(attrs={'type': 'date'}),
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

    Farmers quote their wholesale price per unit (cost_price), available stock,
    and measurement unit. Admin sets the retail listing price on approval.
    """

    class Meta:
        model = Product
        fields = ['category', 'name', 'cost_price', 'stock_quantity', 'unit', 'description', 'image', 'is_active']
        labels = {
            'cost_price': 'Your price per unit (₹)',
            'stock_quantity': 'Available Stock',
            'unit': 'Unit',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Optional details about harvest, quality, freshness...'}),
            'stock_quantity': forms.NumberInput(attrs={'min': '0', 'placeholder': 'e.g. 50'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cost_price'].required = True
        if 'name' in self.fields:
            self.fields['name'].max_length = 100
            self.fields['name'].widget.attrs.update({
                'maxlength': '100',
                'placeholder': 'Produce name (max 100 characters)',
            })
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs.update({'class': 'form-select'})
            elif not isinstance(field.widget, (forms.CheckboxInput,)):
                field.widget.attrs.update({'class': 'form-control'})

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if len(name) > 100:
            raise forms.ValidationError('Product name must not exceed 100 characters.')
        return name


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
