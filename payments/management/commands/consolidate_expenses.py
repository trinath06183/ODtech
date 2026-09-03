from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from payments.models import Expense

User = get_user_model()

class Command(BaseCommand):
    help = "Consolidate and update employee codes on all previous expenses"

    def handle(self, *args, **options):
        expenses = Expense.objects.select_related('submitted_by').all()
        updated_count = 0
        
        users_by_username = {u.username.lower(): u for u in User.objects.all()}
        
        for exp in expenses:
            code = (exp.employee_code or '').strip()
            
            # If empty, assign from submitted_by
            if not code and exp.submitted_by:
                if exp.submitted_by.empid:
                    exp.employee_code = exp.submitted_by.empid
                    exp.save(update_fields=['employee_code'])
                    updated_count += 1
                elif exp.submitted_by.username:
                    exp.employee_code = exp.submitted_by.username
                    exp.save(update_fields=['employee_code'])
                    updated_count += 1
            # If code is a username that has an empid, upgrade it to the empid
            elif code.lower() in users_by_username and users_by_username[code.lower()].empid:
                new_code = users_by_username[code.lower()].empid
                if new_code != code:
                    exp.employee_code = new_code
                    exp.save(update_fields=['employee_code'])
                    updated_count += 1
                    
        self.stdout.write(self.style.SUCCESS(f"Successfully processed {expenses.count()} expenses ({updated_count} updated)."))
