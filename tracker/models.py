import uuid
from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model
User = get_user_model()
from .validators import validate_safe_file

class Order(models.Model):
    STATUS_CHOICES = [
        ('OPEN', 'OPEN (New)'),
        ('SOURCING', 'SOURCING'),
        ('PROCURED', 'PROCURED'),
        ('SHIPPED', 'SHIPPED'),
        ('CLOSED', 'CLOSED'),
    ]
    PAYMENT_CHOICES = [
        ('UNPAID', 'Unpaid'),
        ('PARTIALLY_PAID', 'Partially Paid'),
        ('PAID', 'Paid'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_number = models.CharField(max_length=100, unique=True)
    customer_name = models.CharField(max_length=255)
    customer_phone = models.CharField(max_length=50)
    order_status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='OPEN')
    payment_status = models.CharField(max_length=50, choices=PAYMENT_CHOICES, default='UNPAID')
    order_date = models.DateField(auto_now_add=True)
    remark = models.TextField(blank=True, null=True)
    minimum_profit_margin = models.DecimalField(max_digits=5, decimal_places=2, default=25.00, help_text='Minimum required profit margin (%) for automatic price approval.')
    
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='orders_created')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='orders_updated')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.order_number} - {self.customer_name}"

class Lot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='lots')
    lot_name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='lots_created')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='lots_updated')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.lot_name} (Order: {self.order.order_number})"

class Product(models.Model):
    UOM_CHOICES = [
        ('Pcs', 'Pcs'),
        ('Sets', 'Sets'),
        ('Nos', 'Nos'),
        ('Kgs', 'Kgs'),
        ('Mtr', 'Mtr'),
    ]
    STATUS_CHOICES = [
        ('OPEN', 'OPEN'),
        ('SOURCING', 'SOURCING'),
        ('PROCURED', 'PROCURED'),
        ('SHIPPED', 'SHIPPED'),
        ('RECEIVED', 'RECEIVED'),
        ('CLOSED', 'CLOSED'),
    ]

    # Customer-side stages (what happens between you and the customer)
    CUSTOMER_STAGE_CHOICES = [
        ('REQ_RECEIVED', 'Requirement Received'),
        ('QUOT_GIVEN',   'Quotation Given'),
        ('PO_RECEIVED',  'PO Received'),
        ('PI_GIVEN',     'PI Given'),
        ('PROD_GIVEN',   'Product Given'),
        ('INV_GIVEN',    'Invoice Given'),
    ]

    # Supplier-side stages (what happens between you and the supplier)
    SUPPLIER_STAGE_CHOICES = [
        ('REQ_SEARCHING', 'Requirement Searching'),
        ('QUOT_RECEIVED', 'Quotation Received'),
        ('PO_GIVEN',      'PO Given'),
        ('PI_RECEIVED',   'PI Received'),
        ('PROD_RECEIVED', 'Product Received'),
        ('INV_RECEIVED',  'Invoice Received'),
    ]

    # Combined — kept for validation / display helpers
    STAGE_CHOICES = CUSTOMER_STAGE_CHOICES + SUPPLIER_STAGE_CHOICES
    CUSTOMER_STAGES = {v for v, _ in CUSTOMER_STAGE_CHOICES}
    SUPPLIER_STAGES = {v for v, _ in SUPPLIER_STAGE_CHOICES}

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='products')
    lot = models.ForeignKey(Lot, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    sl_no = models.PositiveIntegerField()
    item_name = models.CharField(max_length=255)
    make_or_model = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    quantity = models.PositiveIntegerField()
    uom = models.CharField(max_length=50, default='Pcs')
    photo_or_document = models.FileField(upload_to='product_docs/', blank=True, null=True, validators=[validate_safe_file])
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='OPEN')
    customer_stage = models.CharField(
        max_length=30,
        choices=CUSTOMER_STAGE_CHOICES,
        blank=True,
        null=True,
        help_text='Current stage on the Customer side for this product.'
    )
    supplier_stage = models.CharField(
        max_length=30,
        choices=SUPPLIER_STAGE_CHOICES,
        blank=True,
        null=True,
        help_text='Current stage on the Supplier side for this product.'
    )
    is_purchased = models.BooleanField(default=False)
    buying_price_ex_gst = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    buying_price_inc_gst = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    gst_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=18.00)
    selling_price_ex_gst = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    selling_price_inc_gst = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    price_approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='products_price_approved')
    price_approved_at = models.DateTimeField(null=True, blank=True)
    remark = models.TextField(blank=True, null=True, help_text='Optional remark or notes for this product.')

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='products_created')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='products_updated')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sl_no']

    def __str__(self):
        return f"{self.item_name} (Order: {self.order.order_number})"

    @property
    def selected_supplier(self):
        return self.supplier_options.filter(is_selected=True).first()

    def save(self, *args, **kwargs):
        is_new_file = False
        if self.photo_or_document:
            if self.pk:
                try:
                    old_instance = self.__class__.objects.get(pk=self.pk)
                    if old_instance.photo_or_document != self.photo_or_document:
                        is_new_file = True
                except self.__class__.DoesNotExist:
                    is_new_file = True
            else:
                is_new_file = True

        if is_new_file:
            from .utils import compress_image_to_target
            self.photo_or_document = compress_image_to_target(self.photo_or_document)

        super().save(*args, **kwargs)

class SupplierCostOption(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='supplier_options')
    supplier_name = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True, null=True)
    contact_number = models.CharField(max_length=50, blank=True, null=True)
    contact_email = models.EmailField(blank=True, null=True)
    description = models.TextField(blank=True, null=True, help_text='Optional description or notes for this supplier option.')
    is_selected = models.BooleanField(default=False)
    
    base_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    gst_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=18.00)
    total_inc_gst = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    product_link = models.URLField(max_length=500, blank=True, null=True, verbose_name="Product Link")
    photo_or_document = models.FileField(upload_to='supplier_quotes/', blank=True, null=True, verbose_name="Photo or Document", validators=[validate_safe_file])

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='supplier_options_created')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='supplier_options_updated')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.supplier_name} - {self.product.item_name}"

    def save(self, *args, **kwargs):
        is_new_file = False
        if self.photo_or_document:
            if self.pk:
                try:
                    old_instance = self.__class__.objects.get(pk=self.pk)
                    if old_instance.photo_or_document != self.photo_or_document:
                        is_new_file = True
                except self.__class__.DoesNotExist:
                    is_new_file = True
            else:
                is_new_file = True

        if is_new_file:
            from .utils import compress_image_to_target
            self.photo_or_document = compress_image_to_target(self.photo_or_document)

        super().save(*args, **kwargs)

class ProductBookmark(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='bookmarks')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='product_bookmarks')
    description = models.TextField(blank=True, null=True, help_text='Why did you bookmark this product?')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('product', 'user')
        ordering = ['-created_at']

    def __str__(self):
        return f"Bookmark: {self.product.item_name} by {self.user.username}"

class ProductExpense(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='expenses')
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    EXPENSE_TYPE_CHOICES = [
        ('PER_UNIT', 'Per Unit'),
        ('TOTAL', 'Total Qty'),
    ]
    expense_type = models.CharField(max_length=20, choices=EXPENSE_TYPE_CHOICES, default='PER_UNIT')
    
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='expenses_created')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='expenses_updated')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.description} - {self.amount} for {self.product.item_name}"

class Task(models.Model):
    PRIORITY_CHOICES = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
        ('CRITICAL', 'Critical')
    ]
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed')
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='tasks', null=True, blank=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='tasks', null=True, blank=True)
    
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='MEDIUM')
    due_date = models.DateTimeField(null=True, blank=True)
    
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='assigned_tasks')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-priority', 'due_date', '-created_at']

    def __str__(self):
        return f"Task: {self.title} ({self.get_status_display()})"

class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    link = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification for {self.user.username}: {self.title}"


class InternalNote(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='internal_notes', null=True, blank=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='internal_notes', null=True, blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='authored_notes')
    content = models.TextField()
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        target = f"Product {self.product_id}" if self.product else f"Order {self.order_id}"
        return f"Note by {self.author} on {target}"

class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('COMMENT', 'Comment'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=100)
    object_id = models.CharField(max_length=255)
    object_repr = models.CharField(max_length=255)
    changes = models.TextField(blank=True, null=True) # Stored as JSON string
    timestamp = models.DateTimeField(auto_now_add=True)
    task = models.ForeignKey(Task, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.action} on {self.model_name} by {self.user}"

class ErrorLog(models.Model):
    reference_id = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    environment = models.CharField(max_length=50, default='production')
    status_code = models.IntegerField(default=500)
    error_type = models.CharField(max_length=255)
    error_message = models.TextField()
    stack_trace = models.TextField()
    url = models.CharField(max_length=2000)
    http_method = models.CharField(max_length=10)
    query_params = models.TextField(blank=True, null=True) # JSON stored as string
    post_data = models.TextField(blank=True, null=True)    # JSON stored as string, sensitive data scrubbed
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='error_logs')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    is_resolved = models.BooleanField(default=False)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.status_code}] {self.error_type} at {self.url} ({self.reference_id})"

class UserFieldVisibility(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='field_visibility')
    
    # Admin-controlled permissions (what the user is ALLOWED to see)
    can_see_selling_price = models.BooleanField(default=True)
    can_see_purchase_price = models.BooleanField(default=True)
    can_see_profit_loss = models.BooleanField(default=True)
    can_see_lot_total = models.BooleanField(default=True)
    can_see_internal_notes = models.BooleanField(default=True)
    
    # User-controlled display preferences (what the user WANTS to see)
    pref_show_selling_price = models.BooleanField(default=True)
    pref_show_purchase_price = models.BooleanField(default=True)
    pref_show_profit_loss = models.BooleanField(default=True)
    pref_show_lot_total = models.BooleanField(default=True)
    pref_show_internal_notes = models.BooleanField(default=True)

    def __str__(self):
        return f"Visibility for {self.user.username}"

class PriceApprovalRequest(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='price_approval_requests')
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='price_requests_made')
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='price_requests_reviewed')
    
    # Proposed new values
    buying_price_ex_gst = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    buying_price_inc_gst = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    gst_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=18.00)
    selling_price_ex_gst = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    selling_price_inc_gst = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    # Supplier option if this was triggered by selecting a supplier
    supplier_option = models.ForeignKey('SupplierCostOption', on_delete=models.SET_NULL, null=True, blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Price Request for {self.product.item_name} by {self.requested_by}"


class OrderExpense(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='expenses')
    expense_name = models.CharField(max_length=255)
    amount_ex_gst = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    gst_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=18.00)
    amount_inc_gst = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    remark = models.TextField(blank=True, null=True)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='order_expenses_created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.expense_name} - {self.order.order_number}"


class UserNote(models.Model):
    """Private note visible only to the owning user."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='personal_notes')
    title = models.CharField(max_length=255)
    content = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"Note by {self.user.username}: {self.title}"


class UserTodo(models.Model):
    """Private to-do task visible only to the owning user."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='personal_todos')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['is_completed', '-created_at']

    def __str__(self):
        return f"Todo by {self.user.username}: {self.title}"

class UserReferenceDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reference_documents')
    note = models.ForeignKey(UserNote, on_delete=models.CASCADE, related_name='documents', null=True, blank=True)
    todo = models.ForeignKey(UserTodo, on_delete=models.CASCADE, related_name='documents', null=True, blank=True)
    document = models.FileField(upload_to='user_references/', validators=[validate_safe_file])
    reference_text = models.CharField(max_length=500, blank=True, help_text="Text box for document reference")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"Doc: {self.reference_text or self.document.name} by {self.user.username}"

class SystemSetting(models.Model):
    key = models.CharField(max_length=255, unique=True)
    value = models.TextField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.key

