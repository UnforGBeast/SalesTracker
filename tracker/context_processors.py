from django.conf import settings
import os
def brand_context(request):
    # Fetch and aggressively clean the exact color word from the .env file
    raw_color = os.getenv('BRAND_COLOR', 'slate').replace("'", "").replace('"', "").strip().lower()
    
    return {
        'BRAND_NAME': os.getenv('BRAND_NAME', 'Zorvia Core').replace("'", "").replace('"', ""),
        'BRAND_COLOR': raw_color,
        'CURRENCY_SYMBOL': os.getenv('CURRENCY_SYMBOL', '₹').replace("'", "").replace('"', ""),
        'BRAND_LOGO': os.getenv('BRAND_LOGO', '/static/default_logo.png'), 
    }