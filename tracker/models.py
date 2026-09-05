import uuid
import colorsys
from django.db import models
from django.utils import timezone
import secrets


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

    is_dead_stock = models.BooleanField(
        default=False, db_index=True,
        help_text="Slow-moving stock flagged for clearance. Still counts as available inventory."
    )
    dead_stock_marked_at = models.DateTimeField(null=True, blank=True)

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


# ---- White-label configuration -------------------------------------------

# Quick-start presets offered in the setup wizard. "value" is the seed accent
# hex; the user can still fine-tune it with a native color picker afterwards.
BRAND_PROFILE_PRESETS = [
    ('textiler', 'Textiler (Banarasi Textile)', '#C8A46E', 'Inventory intelligence for Banarasi textile distribution.'),
    ('slate', 'Slate / Neutral', '#64748b', ''),
    ('indigo', 'Royal Indigo', '#6366f1', ''),
    ('emerald', 'Emerald Green', '#10b981', ''),
    ('rose', 'Rose / Crimson', '#f43f5e', ''),
    ('amber', 'Amber / Gold', '#f59e0b', ''),
    ('sky', 'Sky Blue', '#0ea5e9', ''),
]


def hex_to_rgb(value):
    value = value.lstrip('#')
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return '#%02x%02x%02x' % tuple(max(0, min(255, round(c))) for c in rgb)


def generate_shade_ramp(hex_color):
    """Builds a Tailwind-style 50-950 shade ramp from a single brand hex color,
    so any custom brand color (not just Tailwind's built-in palette names) can
    back `bg-brand-500`-style utility classes via a runtime Tailwind config."""
    r, g, b = hex_to_rgb(hex_color)
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    s = min(1.0, s * 1.05)
    lightness_targets = {
        50: 0.97, 100: 0.94, 200: 0.86, 300: 0.74, 400: 0.60,
        500: max(0.30, min(l, 0.55)), 600: 0.42, 700: 0.34, 800: 0.27, 900: 0.20, 950: 0.12,
    }
    ramp = {}
    for shade, target_l in lightness_targets.items():
        rr, gg, bb = colorsys.hls_to_rgb(h, target_l, s)
        ramp[shade] = rgb_to_hex((rr * 255, gg * 255, bb * 255))
    ramp[500] = hex_color
    return ramp


class SiteConfig(models.Model):
    """Singleton white-label configuration, edited via the first-run setup
    wizard (see views.setup_wizard) and afterwards from the admin. Replaces
    the old .env-only brand vars as the source of truth for the running
    instance; .env values remain the seed defaults shown before setup."""

    brand_name = models.CharField(max_length=100, default='Textiler')
    tagline = models.CharField(max_length=200, blank=True, default='')
    accent_hex = models.CharField(
        max_length=7, default='#C8A46E',
        help_text="Primary brand color as a hex code, e.g. #C8A46E"
    )
    currency_symbol = models.CharField(max_length=5, default='₹')
    logo = models.ImageField(upload_to='branding/', null=True, blank=True)
    is_setup_complete = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site Configuration"
        verbose_name_plural = "Site Configuration"

    def save(self, *args, **kwargs):
        self.pk = 1  # enforce singleton row
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """Fetches the singleton row, creating it on first access. A brand new
        row is seeded from any pre-existing .env brand vars so upgrading an
        already-customized deployment doesn't silently reset its branding;
        a fresh install falls back to the Textiler defaults. Either way
        is_setup_complete stays False until the wizard is actually completed."""
        import os
        preset_hex_by_name = {name: hexval for name, _, hexval, _ in BRAND_PROFILE_PRESETS}
        env_color_name = os.getenv('BRAND_COLOR', '').replace("'", "").replace('"', "").strip().lower()
        defaults = {
            'brand_name': os.getenv('BRAND_NAME', 'Textiler').replace("'", "").replace('"', "").strip() or 'Textiler',
            'accent_hex': preset_hex_by_name.get(env_color_name, '#C8A46E'),
            'currency_symbol': os.getenv('CURRENCY_SYMBOL', '₹').replace("'", "").replace('"', "").strip() or '₹',
        }
        obj, _ = cls.objects.get_or_create(pk=1, defaults=defaults)
        return obj

    @property
    def shade_ramp(self):
        return generate_shade_ramp(self.accent_hex)

    def __str__(self):
        return f"Site Configuration ({self.brand_name})"