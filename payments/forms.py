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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.initial['date'] = datetime.date.today()
            
        standard_choices = list(Expense.EXPENSE_TYPES)
        standard_choices.append(('Custom', (('__custom__', '➕ Add Custom Category...'),)))
        
        self.fields['expense_type'] = forms.ChoiceField(
            choices=standard_choices,
            widget=forms.Select(attrs={
                'class': 'mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 bg-white shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm',
                'x-model': 'category',
                '@change': 'handleCategoryChange()'
            })
        )

    class Meta:
        model = Expense
        fields = ['title', 'employee_code', 'expense_type', 'amount', 'gst_amount', 'date', 'receipt', 'notes']
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
            User = get_user_model()
            if not User.objects.filter(empid=code).exists():
                raise forms.ValidationError("Invalid Employee Code. No such employee exists.")
        return code

    def clean(self):
        cleaned_data = super().clean()
        expense_type = cleaned_data.get('expense_type')
        custom_category = cleaned_data.get('custom_category')
        
        if expense_type == '__custom__':
            if not custom_category:
                self.add_error('custom_category', 'Please specify the custom category name.')
            else:
                cleaned_data['expense_type'] = custom_category.strip()
                
        return cleaned_data
