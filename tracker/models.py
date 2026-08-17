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