from django.conf import settings

def brand_context(request):
    return {
        'BRAND_NAME': getattr(settings, 'BRAND_NAME', 'Zorvia Core'),
        'BRAND_COLOR': getattr(settings, 'BRAND_COLOR', 'slate'),  # Tailwind color family (e.g., slate, indigo, emerald, rose)
        'CURRENCY_SYMBOL': getattr(settings, 'CURRENCY_SYMBOL', '₹'),
        'BRAND_LOGO': getattr(settings, 'BRAND_LOGO', '/static/default_logo.png'),
    }
