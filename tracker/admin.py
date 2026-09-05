from unfold.admin import ModelAdmin
from django.contrib import admin
from django.utils.html import format_html

import csv
from django.http import HttpResponse
from unfold.decorators import action
import os
from django.utils import timezone
from .models import FinishedProduct, ResellerToken, SiteConfig

admin.site.index_title = "Inventory Management"
BRAND_NAME = os.getenv('BRAND_NAME', 'Silk O Zari')
BRAND_COLOR = os.getenv('BRAND_COLOR', 'slate')
CURRENCY_SYMBOL = os.getenv('CURRENCY_SYMBOL', '₹')



@admin.action(description='Generate Report / Export to CSV')
def export_as_csv(self, request, queryset):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="inventory_analytics_report.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Barcode ID', 'Product Type', 'Design Work', 'Weaver', 
        'Current Status', 'Date Entered', 'Date Dispatched', 
        'Sales Channel', 'Destination City', 'Destination State'
    ])
    
    for obj in queryset:
        writer.writerow([
            obj.id, obj.product_type, obj.design_work, obj.weaver_name, 
            obj.status, obj.date_entered, obj.date_dispatched, 
            obj.sales_channel, obj.derived_city, obj.derived_state
        ])
    return response

@admin.action(description='Mark selected items as Dead Stock')
def mark_dead_stock(modeladmin, request, queryset):
    queryset.filter(is_dead_stock=False).update(is_dead_stock=True, dead_stock_marked_at=timezone.now())

@admin.action(description='Unmark selected items as Dead Stock')
def unmark_dead_stock(modeladmin, request, queryset):
    queryset.filter(is_dead_stock=True).update(is_dead_stock=False, dead_stock_marked_at=None)


@admin.register(FinishedProduct)
class FinishedProductAdmin(ModelAdmin):
    # What shows up in the main table
    list_display = ('id', 'product_type','image_thumbnail', 'status_badge', 'dead_stock_badge', 'derived_city', 'date_entered','return_reason')
    list_filter = ('status', 'sales_channel', 'product_type', 'derived_state','return_reason', 'is_dead_stock')
    search_fields = ('id', 'product_type', 'weaver_name', 'design_work', 'pincode','derived_city')
    actions = [mark_dead_stock, unmark_dead_stock]

    date_hierarchy = 'date_entered'

    # Made the preview read-only so it renders as an image, not a file upload button
    readonly_fields = ('id', 'date_entered', 'date_dispatched', 'derived_city', 'derived_state', 'image_preview', 'dead_stock_marked_at')
    # How many items per page before pagination
    list_per_page = 50

    actions_list = ["export_all_to_csv"]

    @action(description="Export to Excel / CSV")
    def export_all_to_csv(self, request):
        """ Exports all items currently matching the user's active filters """
        
        # Get the queryset of whatever is currently filtered on the screen
        queryset = self.get_changelist_instance(request).get_queryset(request)
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="silk_o_zari_inventory_report.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Barcode ID', 'Product Type', 'Design Work', 'Weaver', 
            'Current Status', 'Date Entered', 'Date Dispatched', 
            'Sales Channel', 'Destination City', 'Destination State'
        ])
        
        for obj in queryset:
            writer.writerow([
                obj.id, obj.product_type, obj.design_work, obj.weaver_name, 
                obj.status, obj.date_entered, obj.date_dispatched, 
                obj.sales_channel, obj.derived_city, obj.derived_state
            ])
        return response
        
    # (Keep your existing status_badge function here)

    # Organizes the detail view into clean sections
    fieldsets = (
        ('Product Identification', {
            'fields': ('id', 'product_type', 'design_work','product_image', 'image_preview', 'weaver_name')
        }),
        ('Inventory Status', {
            'fields': ('status','return_reason', 'date_entered', 'is_dead_stock', 'dead_stock_marked_at')
        }),
        ('Dispatch Tracking Data', {
            'fields': ('sales_channel', 'date_dispatched', 'pincode', 'derived_city', 'derived_state'),
            'classes': ('collapse',), # This hides the dispatch section under a dropdown if empty
        }),
    )
    @admin.display(description='Photo')
    def image_thumbnail(self, obj):
        if obj.product_image:
            return format_html('<img src="{}" style="height: 40px; border-radius: 4px;" />', obj.product_image.url)
        return "-"

    @admin.display(description='Preview')
    def image_preview(self, obj):
        if obj.product_image:
            return format_html('<img src="{}" style="max-height: 300px; border-radius: 8px;" />', obj.product_image.url)
        return "No image uploaded"

    @admin.display(description='Dead Stock', boolean=False)
    def dead_stock_badge(self, obj):
        if obj.is_dead_stock:
            return format_html('<span style="color: white; background-color: #78716c; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 12px;">{}</span>', 'DEAD STOCK')
        return "-"

    def save_model(self, request, obj, form, change):
        # Auto-stamp the marked-at timestamp whenever the checkbox is toggled
        # directly on the detail page (the bulk actions do this too).
        if 'is_dead_stock' in form.changed_data:
            obj.dead_stock_marked_at = timezone.now() if obj.is_dead_stock else None
        super().save_model(request, obj, form, change)

    # Custom HTML to create colored status tags
    @admin.display(description='Live Status')
    def status_badge(self, obj):
        # format_html() with zero placeholders raises TypeError on Django 6.1
        # ("args or kwargs must be provided") -- always pass the label through
        # as an argument, even when it's a fixed string, so it's never called bare.
        if obj.status == 'IN_STOCK':
            return format_html('<span style="color: white; background-color: #10b981; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 12px;">{}</span>', 'IN STOCK')
        elif obj.status == 'DISPATCHED':
            return format_html('<span style="color: white; background-color: #3b82f6; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 12px;">{}</span>', 'DISPATCHED')
        return format_html('<span style="color: white; background-color: #ef4444; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 12px;">{}</span>', obj.status)

@admin.register(ResellerToken)
class ResellerTokenAdmin(admin.ModelAdmin):
    list_display = ('reseller_name', 'is_active', 'created_at', 'token')
    list_filter = ('is_active',)
    search_fields = ('reseller_name',)
    # Make the token read-only so it can't be accidentally edited
    readonly_fields = ('token',)


@admin.register(SiteConfig)
class SiteConfigAdmin(ModelAdmin):
    """Singleton editor for the white-label settings normally set once via the
    /setup/ wizard. Lets staff re-brand the instance later without re-running it."""
    list_display = ('brand_name', 'accent_hex', 'currency_symbol', 'is_setup_complete', 'updated_at')
    readonly_fields = ('updated_at',)
    fieldsets = (
        ('Branding', {
            'fields': ('brand_name', 'tagline', 'accent_hex', 'currency_symbol', 'logo')
        }),
        ('Status', {
            'fields': ('is_setup_complete', 'updated_at')
        }),
    )

    def has_add_permission(self, request):
        # Singleton: only ever one row (pk=1), created by SiteConfig.load().
        return not SiteConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # Skip the list page entirely and go straight to editing the one row.
        config = SiteConfig.load()
        from django.shortcuts import redirect
        from django.urls import reverse
        return redirect(reverse('admin:tracker_siteconfig_change', args=[config.pk]))