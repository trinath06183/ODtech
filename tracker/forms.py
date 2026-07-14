from django import forms
from .models import Order, Lot, Product, SupplierCostOption

class TailwindMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            existing_class = field.widget.attrs.get('class', '')
            if isinstance(field.widget, forms.CheckboxInput):
                css = 'w-4 h-4 text-indigo-600 bg-white border-gray-300 rounded focus:ring-indigo-500 focus:ring-2'
            elif isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
                css = 'mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-md bg-white border'
            elif isinstance(field.widget, forms.FileInput):
                css = 'block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-medium file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100'
            elif isinstance(field.widget, forms.Textarea):
                css = 'shadow-sm focus:ring-indigo-500 focus:border-indigo-500 block w-full sm:text-sm border-gray-300 rounded-md border p-2'
                field.widget.attrs['rows'] = 3
            else:
                css = 'shadow-sm focus:ring-indigo-500 focus:border-indigo-500 block w-full sm:text-sm border-gray-300 rounded-md border p-2'
            field.widget.attrs['class'] = (existing_class + ' ' + css).strip()

class TailwindModelForm(TailwindMixin, forms.ModelForm):
    pass

class TailwindBasicForm(TailwindMixin, forms.Form):
    pass

class OrderForm(TailwindModelForm):
    class Meta:
        model = Order
        fields = ['order_number', 'customer_name', 'customer_phone', 'order_status', 'payment_status', 'minimum_profit_margin', 'remark']

class LotForm(TailwindModelForm):
    class Meta:
        model = Lot
        fields = ['lot_name', 'description']

class ProductForm(TailwindModelForm):
    UOM_SUGGESTIONS = ['Pcs', 'Sets', 'Nos', 'Kgs', 'Mtr', 'Ltr', 'Sq.Ft', 'Sq.Mtr', 'Cu.Mtr', 'Ft', 'Inch', 'Ton', 'Box', 'Roll', 'Bundle', 'Pair', 'Bag']

    class Meta:
        model = Product
        fields = ['sl_no', 'item_name', 'make_or_model', 'description', 'quantity', 'uom', 'lot', 'photo_or_document', 'status', 'remark']
        widgets = {
            'uom': forms.TextInput(attrs={'list': 'uom-suggestions', 'placeholder': 'e.g. Pcs, Kgs, Mtr...'}),
        }

    def __init__(self, *args, **kwargs):
        order = kwargs.pop('order', None)
        super().__init__(*args, **kwargs)
        if order:
            self.fields['lot'].queryset = Lot.objects.filter(order=order)
        elif self.instance and self.instance.pk and self.instance.order:
            self.fields['lot'].queryset = Lot.objects.filter(order=self.instance.order)

class SupplierCostOptionForm(TailwindModelForm):
    product_link = forms.CharField(required=False, max_length=2000, widget=forms.TextInput(attrs={'placeholder': 'https://...'}))

    class Meta:
        model = SupplierCostOption
        fields = ['supplier_name', 'location', 'contact_number', 'contact_email', 'description', 'base_price', 'gst_percentage', 'total_inc_gst', 'product_link', 'is_selected', 'photo_or_document']
        widgets = {
            'supplier_name': forms.TextInput(attrs={'list': 'supplier-suggestions', 'oninput': 'autofillSupplierDetails(this)'}),
            'base_price': forms.NumberInput(attrs={'x-model': 'basePrice', '@input': 'calcForward()', 'step': '0.01'}),
            'gst_percentage': forms.NumberInput(attrs={'x-model': 'gstPercent', '@input': 'calcForward()', 'step': '0.01'}),
            'total_inc_gst': forms.NumberInput(attrs={'x-model': 'totalPrice', '@input': 'calcReverse()', 'step': '0.01'}),
        }

    def clean_product_link(self):
        url = self.cleaned_data.get('product_link')
        if not url:
            return url

        url = url.strip()
        
        # 1. Protocol Validation
        if not (url.startswith('http://') or url.startswith('https://')):
            if url.startswith('www.'):
                url = 'https://' + url
            else:
                url = 'https://' + url

        # 2. Length Check and Shortening
        if len(url) > 200:
            import urllib.request
            import urllib.parse
            try:
                # tinyurl api expects the url to be urlencoded
                encoded_url = urllib.parse.quote(url)
                req_url = f'https://tinyurl.com/api-create.php?url={encoded_url}'
                with urllib.request.urlopen(req_url, timeout=5) as response:
                    if response.status == 200:
                        shortened = response.read().decode('utf-8')
                        if shortened:
                            url = shortened
            except Exception as e:
                print(f"Failed to shorten URL: {e}")

        return url

class ProductPricingForm(TailwindModelForm):
    profit_amount = forms.DecimalField(required=False, max_digits=12, decimal_places=2, widget=forms.NumberInput(attrs={'x-model': 'profitAmount', '@input': 'calcFromProfitAmount()', 'step': '0.01'}))
    profit_percentage = forms.DecimalField(required=False, max_digits=5, decimal_places=2, widget=forms.NumberInput(attrs={'x-model': 'profitPercent', '@input': 'calcFromProfitPercent()', 'step': '0.01'}))

    class Meta:
        model = Product
        fields = ['buying_price_ex_gst', 'buying_price_inc_gst', 'gst_percentage', 'selling_price_ex_gst', 'selling_price_inc_gst']
        widgets = {
            'buying_price_ex_gst': forms.NumberInput(attrs={'x-model': 'buyingPriceExGst', '@input': 'calcBuyingForward()', 'step': '0.01'}),
            'gst_percentage': forms.NumberInput(attrs={'x-model': 'gstPercent', '@input': 'calcAllForward()', 'step': '0.01'}),
            'buying_price_inc_gst': forms.NumberInput(attrs={'x-model': 'buyingPriceIncGst', '@input': 'calcBuyingReverse()', 'step': '0.01'}),
            'selling_price_ex_gst': forms.NumberInput(attrs={'x-model': 'sellingPriceExGst', '@input': 'calcSellingForward()', 'step': '0.01'}),
            'selling_price_inc_gst': forms.NumberInput(attrs={'x-model': 'sellingPriceIncGst', '@input': 'calcSellingReverse()', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].required = False

    def clean(self):
        cleaned_data = super().clean()
        defaults = {
            'buying_price_ex_gst': 0.00,
            'buying_price_inc_gst': 0.00,
            'gst_percentage': 18.00,
            'selling_price_ex_gst': 0.00,
            'selling_price_inc_gst': 0.00,
        }
        for field, default_val in defaults.items():
            if cleaned_data.get(field) is None:
                cleaned_data[field] = default_val
        return cleaned_data

class CSVUploadForm(TailwindBasicForm):
    lot = forms.ModelChoiceField(queryset=Lot.objects.none(), required=False, empty_label="-- No Lot (Unassigned) --", label="Assign to Lot", help_text="Optional: Select a lot to assign these products to.")
    csv_file = forms.FileField(label='Select CSV File', help_text="Upload a CSV file containing product data.")

    def __init__(self, *args, **kwargs):
        order = kwargs.pop('order', None)
        super().__init__(*args, **kwargs)
        if order:
            self.fields['lot'].queryset = Lot.objects.filter(order=order)

# --- User Management Forms ---
from django.contrib.auth import get_user_model
User = get_user_model()
from django.contrib.auth.forms import UserCreationForm, UserChangeForm, SetPasswordForm

from .models import UserFieldVisibility

class AdminUserCreationForm(TailwindMixin, UserCreationForm):
    can_see_selling_price = forms.BooleanField(required=False, initial=True, label="Can see Selling Price")
    can_see_purchase_price = forms.BooleanField(required=False, initial=True, label="Can see Purchase Price")
    can_see_profit_loss = forms.BooleanField(required=False, initial=True, label="Can see Profit & Loss")
    can_see_lot_total = forms.BooleanField(required=False, initial=True, label="Can see Lot Total")
    can_see_internal_notes = forms.BooleanField(required=False, initial=True, label="Can see Internal Notes")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ('email', 'first_name', 'last_name', 'is_staff', 'is_superuser', 'is_active')

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            fv, created = UserFieldVisibility.objects.get_or_create(user=user)
            fv.can_see_selling_price = self.cleaned_data.get('can_see_selling_price', True)
            fv.can_see_purchase_price = self.cleaned_data.get('can_see_purchase_price', True)
            fv.can_see_profit_loss = self.cleaned_data.get('can_see_profit_loss', True)
            fv.can_see_lot_total = self.cleaned_data.get('can_see_lot_total', True)
            fv.can_see_internal_notes = self.cleaned_data.get('can_see_internal_notes', True)
            fv.save()
        return user


class AdminUserChangeForm(TailwindMixin, UserChangeForm):
    password = None # Hide password edit field, will provide a separate reset button
    
    can_see_selling_price = forms.BooleanField(required=False, label="Can see Selling Price")
    can_see_purchase_price = forms.BooleanField(required=False, label="Can see Purchase Price")
    can_see_profit_loss = forms.BooleanField(required=False, label="Can see Profit & Loss")
    can_see_lot_total = forms.BooleanField(required=False, label="Can see Lot Total")
    can_see_internal_notes = forms.BooleanField(required=False, label="Can see Internal Notes")
    
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'is_superuser', 'is_active')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and hasattr(self.instance, 'field_visibility'):
            fv = self.instance.field_visibility
            self.fields['can_see_selling_price'].initial = fv.can_see_selling_price
            self.fields['can_see_purchase_price'].initial = fv.can_see_purchase_price
            self.fields['can_see_profit_loss'].initial = fv.can_see_profit_loss
            self.fields['can_see_lot_total'].initial = fv.can_see_lot_total
            self.fields['can_see_internal_notes'].initial = fv.can_see_internal_notes

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            fv, created = UserFieldVisibility.objects.get_or_create(user=user)
            fv.can_see_selling_price = self.cleaned_data.get('can_see_selling_price', True)
            fv.can_see_purchase_price = self.cleaned_data.get('can_see_purchase_price', True)
            fv.can_see_profit_loss = self.cleaned_data.get('can_see_profit_loss', True)
            fv.can_see_lot_total = self.cleaned_data.get('can_see_lot_total', True)
            fv.can_see_internal_notes = self.cleaned_data.get('can_see_internal_notes', True)
            fv.save()
        return user

class AdminPasswordResetForm(TailwindMixin, SetPasswordForm):
    pass

class UserProfileForm(TailwindModelForm):
    pref_show_selling_price = forms.BooleanField(required=False, label="Show Selling Price")
    pref_show_purchase_price = forms.BooleanField(required=False, label="Show Purchase Price")
    pref_show_profit_loss = forms.BooleanField(required=False, label="Show Profit & Loss")
    pref_show_lot_total = forms.BooleanField(required=False, label="Show Lot Total")
    pref_show_internal_notes = forms.BooleanField(required=False, label="Show Internal Notes")

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and hasattr(self.instance, 'field_visibility'):
            fv = self.instance.field_visibility
            self.fields['pref_show_selling_price'].initial = fv.pref_show_selling_price
            self.fields['pref_show_purchase_price'].initial = fv.pref_show_purchase_price
            self.fields['pref_show_profit_loss'].initial = fv.pref_show_profit_loss
            self.fields['pref_show_lot_total'].initial = fv.pref_show_lot_total
            self.fields['pref_show_internal_notes'].initial = fv.pref_show_internal_notes
        else:
            # For superusers who might not have a field_visibility record yet
            self.fields['pref_show_selling_price'].initial = True
            self.fields['pref_show_purchase_price'].initial = True
            self.fields['pref_show_profit_loss'].initial = True
            self.fields['pref_show_lot_total'].initial = True
            self.fields['pref_show_internal_notes'].initial = True

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            from .models import UserFieldVisibility
            fv, created = UserFieldVisibility.objects.get_or_create(user=user)
            fv.pref_show_selling_price = self.cleaned_data.get('pref_show_selling_price', True)
            fv.pref_show_purchase_price = self.cleaned_data.get('pref_show_purchase_price', True)
            fv.pref_show_profit_loss = self.cleaned_data.get('pref_show_profit_loss', True)
            fv.pref_show_lot_total = self.cleaned_data.get('pref_show_lot_total', True)
            fv.pref_show_internal_notes = self.cleaned_data.get('pref_show_internal_notes', True)
            fv.save()
        return user


