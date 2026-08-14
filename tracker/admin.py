from unfold.admin import ModelAdmin
from django.contrib import admin
from django.utils.html import format_html
from .models import FinishedProduct


# Customize Global Admin Headers
admin.site.site_header = "Silk O Zari Administration"
admin.site.site_title = "Silk O Zari Portal"
admin.site.index_title = "Inventory Dashboard"

@admin.register(FinishedProduct)
class FinishedProductAdmin(ModelAdmin):
    # What shows up in the main table
    list_display = ('id', 'product_type', 'design_work', 'weaver_name', 'status_badge', 'derived_city', 'date_entered')
    
    # Adds a calendar filter at the top
    date_hierarchy = 'date_entered'
    
    # Side panel filters
    list_filter = ('status', 'sales_channel', 'product_type', 'derived_state')
    search_fields = ('id', 'product_type', 'design_work', 'weaver_name', 'pincode', 'derived_city')
    
    readonly_fields = ('id', 'date_entered', 'date_dispatched', 'derived_city', 'derived_state')
    
    # How many items per page before pagination
    list_per_page = 50

    # Organizes the detail view into clean sections
    fieldsets = (
        ('Product Identification', {
            'fields': ('id', 'product_type', 'design_work', 'weaver_name')
        }),
        ('Inventory Status', {
            'fields': ('status', 'date_entered')
        }),
        ('Dispatch Tracking Data', {
            'fields': ('sales_channel', 'date_dispatched', 'pincode', 'derived_city', 'derived_state'),
            'classes': ('collapse',), # This hides the dispatch section under a dropdown if empty
        }),
    )

    # Custom HTML to create colored status tags
    @admin.display(description='Live Status')
    def status_badge(self, obj):
        if obj.status == 'IN_STOCK':
            return format_html('<span style="color: white; background-color: #10b981; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 12px;">IN STOCK</span>')
        elif obj.status == 'DISPATCHED':
            return format_html('<span style="color: white; background-color: #3b82f6; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 12px;">DISPATCHED</span>')
        return format_html('<span style="color: white; background-color: #ef4444; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 12px;">{}</span>', obj.status)