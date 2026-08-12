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

class FinishedProduct(models.Model):
    # Core ID used in the QR Code
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Product Details
    product_type = models.CharField(max_length=50, help_text="e.g., SUIT, SAREE, GHARARA")
    design_work = models.CharField(max_length=100, blank=True, null=True, help_text="e.g., JANGAL KADWA")
    weaver_name = models.CharField(max_length=100, blank=True, null=True)
    
    # Lifecycle Tracking
    status = models.CharField(max_length=20, choices=InventoryStatus.choices, default=InventoryStatus.IN_STOCK)
    date_entered = models.DateTimeField(default=timezone.now)
    
    # Dispatch Details
    date_dispatched = models.DateTimeField(null=True, blank=True)
    sales_channel = models.CharField(max_length=20, choices=SalesChannel.choices, null=True, blank=True)
    pincode = models.CharField(max_length=6, null=True, blank=True)
    derived_state = models.CharField(max_length=50, null=True, blank=True)
    derived_city = models.CharField(max_length=50, null=True, blank=True)

    def __str__(self):
        return f"{self.product_type} - {self.id}"