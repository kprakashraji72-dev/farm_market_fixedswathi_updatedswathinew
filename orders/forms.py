from django import forms
from .models import Order


class CheckoutForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ['delivery_address', 'delivery_phone', 'delivery_latitude', 'delivery_longitude']
        widgets = {
            'delivery_address': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Full delivery address'}),
            'delivery_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contact phone number'}),
            # Populated by JS (navigator.geolocation) on the checkout page, not typed by the user.
            # Both are optional — if geolocation permission is denied, auto-assign just falls
            # back to picking the least-busy driver instead of the nearest one.
            'delivery_latitude': forms.HiddenInput(),
            'delivery_longitude': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['delivery_latitude'].required = False
        self.fields['delivery_longitude'].required = False


class TrackOrderLookupForm(forms.Form):
    """Public, no-login lookup: order number + the mobile number used at checkout."""
    order_id = forms.IntegerField(
        label='Order Number',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 1042'}),
    )
    delivery_phone = forms.CharField(
        label='Mobile Number',
        max_length=20,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Mobile number used at checkout'}),
    )
