from django.contrib import admin
from .models import FinishedProduct

@admin.register(FinishedProduct)
class FinishedProductAdmin(admin.ModelAdmin):
    # What columns show up in the table
    list_display = ('id', 'product_type', 'status', 'derived_city', 'date_entered')
    
    # Creates a filter sidebar on the right
    list_filter = ('status', 'sales_channel', 'product_type')
    
    # Adds a search bar at the top
    search_fields = ('id', 'product_type', 'weaver_name', 'pincode', 'derived_city')
    
    # Makes the fields read-only so workers don't accidentally overwrite QR IDs
    readonly_fields = ('id', 'date_entered', 'date_dispatched', 'derived_city', 'derived_state')