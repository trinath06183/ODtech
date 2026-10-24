import datetime
from django import forms
from django.contrib.auth import get_user_model
from .models import Expense

class ExpenseForm(forms.ModelForm):
    custom_category = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'mt-2 block w-full rounded-md border border-gray-300 px-3 py-2 bg-white shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm',
            'placeholder': 'Enter custom category name',
            'x-show': "category === '__custom__'",
            'x-cloak': 'true'
        })
    )

    is_confidential = forms.BooleanField(
        required=False,
        label="Mark as Confidential",
        widget=forms.CheckboxInput(attrs={
            'class': 'h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 cursor-pointer',
            'id': 'id_is_confidential',
        })
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.initial['date'] = datetime.date.today()
        else:
            self.initial['is_confidential'] = self.instance.is_confidential or self.instance.is_fixed_cost

        from .models import user_can_view_fixed_costs
        can_view_fc = user_can_view_fixed_costs(self.user) if self.user else False

        if can_view_fc:
            categories_to_show = list(Expense.EXPENSE_TYPES)
        else:
            categories_to_show = [('Daily Expenses', Expense.DAILY_EXPENSES)]
            
        standard_choices = [('', '-- Select Category --')] + categories_to_show
        standard_choices.append(('Custom', (('__custom__', '➕ Add Custom Category...'),)))
        
        self.fields['expense_type'] = forms.ChoiceField(
            choices=standard_choices,
            required=True,
            widget=forms.Select(attrs={
                'class': 'mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 bg-white shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm',
                'x-model': 'category',
                '@change': 'handleCategoryChange()'
            })
        )

    class Meta:
        model = Expense
        fields = ['title', 'employee_code', 'expense_type', 'is_confidential', 'amount', 'gst_amount', 'date', 'receipt', 'notes']
        widgets = {
            'employee_code': forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 bg-white shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm', 'list': 'employee-code-suggestions'}),
            'title': forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 bg-white shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
            'amount': forms.NumberInput(attrs={'class': 'mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 bg-white shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
            'gst_amount': forms.NumberInput(attrs={'class': 'mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 bg-white shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 bg-white shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'class': 'mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 bg-white shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
            'receipt': forms.FileInput(attrs={'class': 'mt-1 block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100'})
        }

    def clean_employee_code(self):
        code = self.cleaned_data.get('employee_code')
        if code:
            code = code.strip()
            if code.upper() in ['OFFICE', 'OFFICIAL', 'COMPANY']:
                return 'OFFICE'
            User = get_user_model()
            from django.db.models import Q
            matched = User.objects.filter(Q(empid__iexact=code) | Q(username__iexact=code)).first()
            if not matched:
                raise forms.ValidationError("Invalid Employee Code. Enter a valid employee code or 'OFFICE'.")
            if matched.empid:
                return matched.empid.strip()
            return matched.username.strip()
        return code

    def clean(self):
        cleaned_data = super().clean()
        expense_type = cleaned_data.get('expense_type')
        custom_category = cleaned_data.get('custom_category')
        is_confidential = cleaned_data.get('is_confidential', False)
        
        if expense_type == '__custom__':
            if not custom_category:
                self.add_error('custom_category', 'Please specify the custom category name.')
            else:
                cleaned_data['expense_type'] = custom_category.strip()
                expense_type = cleaned_data['expense_type']

        if Expense.is_fixed_cost_category(expense_type):
            cleaned_data['is_confidential'] = True
            is_confidential = True

        from .models import user_can_view_fixed_costs
        can_view_fc = user_can_view_fixed_costs(self.user) if self.user else False
        if not can_view_fc:
            if is_confidential:
                self.add_error('is_confidential', 'You do not have permission to mark expenses as confidential.')
            if Expense.is_fixed_cost_category(expense_type):
                self.add_error('expense_type', 'You do not have permission to submit or assign confidential / Fixed Cost expenses.')
                
        return cleaned_data
