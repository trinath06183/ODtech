import datetime
from django import forms
from django.contrib.auth import get_user_model
from .models import Expense

class ExpenseForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.initial['date'] = datetime.date.today()

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
            'expense_type': forms.Select(attrs={
                'class': 'mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 bg-white shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm',
                'x-model': 'category',
                '@change': 'handleCategoryChange()'
            }),
            'receipt': forms.FileInput(attrs={'class': 'mt-1 block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100'})
        }

    def clean_employee_code(self):
        code = self.cleaned_data.get('employee_code')
        if code:
            User = get_user_model()
            if not User.objects.filter(empid=code).exists():
                raise forms.ValidationError("Invalid Employee Code. No such employee exists.")
        return code
