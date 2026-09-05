import json
from django.templatetags.static import static
from .models import SiteConfig


def brand_context(request):
    """Exposes the running instance's white-label branding to every template.
    Backed by the SiteConfig singleton (DB) rather than .env alone, so it can
    be changed at runtime from /setup/ or the admin without a restart.

    BRAND_COLOR is always the literal string 'brand' -- a Tailwind color name
    that only exists because BRAND_TAILWIND_CONFIG (below) defines it via a
    runtime `tailwind.config`. That means every existing `bg-{{ BRAND_COLOR }}-500`
    style template class keeps working unchanged, but now resolves to whatever
    hex color this instance actually picked, not one of a fixed set of names.
    """
    config = SiteConfig.load()

    return {
        'BRAND_NAME': config.brand_name,
        'BRAND_TAGLINE': config.tagline,
        'BRAND_COLOR': 'brand',
        'BRAND_ACCENT_HEX': config.accent_hex,
        'CURRENCY_SYMBOL': config.currency_symbol,
        'BRAND_LOGO': config.logo.url if config.logo else static('tracker/logo-default.svg'),
        'SETUP_COMPLETE': config.is_setup_complete,
        # Drop straight into a <script>tailwind.config = {{ BRAND_TAILWIND_CONFIG|safe }}</script>
        # placed right after the Tailwind CDN <script> tag.
        'BRAND_TAILWIND_CONFIG': json.dumps({
            'theme': {'extend': {'colors': {'brand': {str(k): v for k, v in config.shade_ramp.items()}}}}
        }),
    }
