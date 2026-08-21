import uuid
from django.db import models
from django.utils import timezone

class InventoryStatus(models.TextChoices):
    IN_STOCK = 'IN_STOCK', 'In Stock'
    DISPATCHED = 'DISPATCHED', 'Dispatched'
    RETURNED = 'RETURNED', 'Returned'

class SalesChannel(models.TextChoices):
    RETAIL = 'RETAIL', 'Retail Shop'
    WHOLESALE = 'WHOLESALE', 'Wholesale B2B'
    ONLINE = 'ONLINE', 'Online E-commerce'

RETURN_REASONS = [
    ('UNSOLD', 'Unsold / Stock Swap'),
    ('DEFECTIVE', 'Defective / Damaged'),
    ('CANCELED', 'Customer Canceled'),
    ('WRONG_ITEM', 'Wrong Item Shipped'),
    ('OTHER', 'Other'),
]

class FinishedProduct(models.Model):
    # Allows both standard UUIDs AND custom printed text QR strings
    id = models.CharField(primary_key=True, max_length=100, default=uuid.uuid4, editable=True)
    product_image = models.ImageField(upload_to='product_images/', null=True, blank=True)
    
    product_type = models.CharField(max_length=50,db_index=True)
    design_work = models.CharField(max_length=100, db_index=True, blank=True, null=True)
    weaver_name = models.CharField(max_length=100, db_index=True, blank=True, null=True)
 # Inside your FinishedProduct class, add this below your other fields:
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Selling price of the item")
    return_reason = models.CharField(max_length=50, choices=RETURN_REASONS, null=True, blank=True)
    status = models.CharField(max_length=20, choices=InventoryStatus.choices, default=InventoryStatus.IN_STOCK)
    date_entered = models.DateTimeField(default=timezone.now)
    
    date_dispatched = models.DateTimeField(null=True, blank=True)
    sales_channel = models.CharField(max_length=20, choices=SalesChannel.choices, null=True, blank=True)
    pincode = models.CharField(max_length=6, null=True, db_index=True, blank=True)
    derived_state = models.CharField(max_length=50, null=True, db_index=True, blank=True)
    derived_city = models.CharField(max_length=50, null=True, db_index=True, blank=True)



    def __str__(self):
        return f"{self.product_type} - {self.id}"

class ResellerToken(models.Model):
    reseller_name = models.CharField(max_length=100, help_text="Name of the reseller company")
    token = models.CharField(max_length=64, unique=True, blank=True, help_text="Auto-generated secure access token")
    is_active = models.BooleanField(default=True, help_text="Uncheck this to instantly revoke access")
    created_at = models.DateTimeField(auto_now_add=True)
    
    def save(self, *args, **kwargs):
        # Automatically generate a 32-byte secure token if one doesn't exist
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)

    def __str__(self):
        status_label = "Active" if self.is_active else "Revoked"
        return f"{self.reseller_name} ({status_label})"