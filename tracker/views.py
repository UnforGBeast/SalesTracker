import os
import re
import csv
import io
import sys
import mimetypes

from django.conf import settings
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.core.files.base import ContentFile
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse, FileResponse, Http404
from django.templatetags.static import static
from django.utils import timezone
from django.db.models import Sum, Q

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
import requests
from PIL import Image
from django.core.files.uploadedfile import InMemoryUploadedFile

from .models import FinishedProduct, ResellerToken, InventoryStatus, SiteConfig, BRAND_PROFILE_PRESETS


LOGIN_URL = 'scanner_login'
BRAND_ASSET_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp', '.svg')


@login_required(login_url=LOGIN_URL)
def inventory_list_view(request):
    # 1. Get ALL filter values from the URL
    status_filter = request.GET.get('status')
    search_query = request.GET.get('search')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    pincode = request.GET.get('pincode')
    dead_stock_filter = request.GET.get('dead_stock')

    # 2. Start with all products
    products = FinishedProduct.objects.all().order_by('-date_entered')

    # 3. Apply Filters sequentially
    if status_filter:
        products = products.filter(status=status_filter)
    if search_query:
        products = products.filter(
            Q(id__icontains=search_query) |
            Q(weaver_name__icontains=search_query) |
            Q(design_work__icontains=search_query)
        )
    if start_date:
        products = products.filter(date_entered__gte=start_date)
    if end_date:
        products = products.filter(date_entered__lte=end_date)
    if min_price:
        products = products.filter(price__gte=min_price)
    if max_price:
        products = products.filter(price__lte=max_price)
    if pincode:
        products = products.filter(pincode__icontains=pincode)
    if dead_stock_filter == 'only':
        products = products.filter(is_dead_stock=True)
    elif dead_stock_filter == 'exclude':
        products = products.filter(is_dead_stock=False)

    # ---------------------------------------------------------
    # NEW: Crash-Proof CSV Export
    # ---------------------------------------------------------
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="inventory_report.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Barcode ID', 'Product Type', 'Design Work', 'Weaver',
            'Price', 'Current Status', 'Dead Stock', 'Date Entered', 'Date Dispatched',
            'Sales Channel', 'Destination Pincode', 'Destination City', 'Destination State'
        ])

        for obj in products:
            # Safely get dates if they exist
            date_in = obj.date_entered.strftime('%Y-%m-%d') if getattr(obj, 'date_entered', None) else ''
            date_out = obj.date_dispatched.strftime('%Y-%m-%d') if getattr(obj, 'date_dispatched', None) else ''

            writer.writerow([
                getattr(obj, 'id', ''),
                getattr(obj, 'product_type', ''),
                getattr(obj, 'design_work', ''),
                getattr(obj, 'weaver_name', ''),
                getattr(obj, 'price', 0.0),
                getattr(obj, 'status', ''),
                'YES' if getattr(obj, 'is_dead_stock', False) else '',
                date_in,
                date_out,
                getattr(obj, 'sales_channel', ''),
                getattr(obj, 'pincode', ''),
                getattr(obj, 'derived_city', ''),
                getattr(obj, 'derived_state', '')
            ])
        return response

    # 4. Calculate global dashboard metrics
    global_stock = FinishedProduct.objects.all()
    in_stock = global_stock.filter(status__in=['IN_STOCK', 'RETURNED'])
    dispatched = global_stock.filter(status='DISPATCHED')
    dead_stock = global_stock.filter(is_dead_stock=True, status__in=['IN_STOCK', 'RETURNED'])

    inventory_value = in_stock.aggregate(Sum('price'))['price__sum'] or 0
    total_sales = dispatched.aggregate(Sum('price'))['price__sum'] or 0
    dead_stock_value = dead_stock.aggregate(Sum('price'))['price__sum'] or 0

    # 5. Pass everything back to the template
    context = {
        'products': products,
        'inventory_value': inventory_value,
        'stock_count': in_stock.count(),
        'total_sales': total_sales,
        'sales_count': dispatched.count(),
        'dead_stock_count': dead_stock.count(),
        'dead_stock_value': dead_stock_value,
        'current_status': status_filter,
        'search_query': search_query or '',
        'start_date': start_date or '',
        'end_date': end_date or '',
        'min_price': min_price or '',
        'max_price': max_price or '',
        'pincode': pincode or '',
        'dead_stock_filter': dead_stock_filter or '',
    }

    return render(request, 'inventory_list.html', context)


def is_valid_qr(qr_id):
    """
    Validates QR format: 3-4 letters (Company) - 3 letters (Area) - Alphanumeric (Product+Noise)
    Example match: SOZ-LKO-TX8492
    """
    pattern = r'^[A-Z]{3,4}-[A-Z]{3}-[A-Z0-9]{4,10}$'
    return re.match(pattern, qr_id) is not None


def compress_image(uploaded_image):
    """ Resizes and compresses an image before saving to disk """
    img = Image.open(uploaded_image)

    # Strip alpha channels (transparency) if it's a PNG, as JPEGs don't support it
    if img.mode != 'RGB':
        img = img.convert('RGB')

    # Resize the image so its longest edge is max 1200px (keeps aspect ratio)
    img.thumbnail((1200, 1200), Image.Resampling.LANCZOS)

    output = io.BytesIO()

    # Compress and save to the memory buffer as a JPEG with 70% quality
    img.save(output, format='JPEG', quality=70, optimize=True)
    output.seek(0)

    # Construct a new Django file object with the compressed data
    compressed_file = InMemoryUploadedFile(
        output,
        'ImageField',
        f"{uploaded_image.name.split('.')[0]}_compressed.jpg",
        'image/jpeg',
        sys.getsizeof(output),
        None
    )
    return compressed_file


@login_required(login_url=LOGIN_URL)
def scanner_ui(request):
    return render(request, 'scanner.html', {'initial_mode': request.GET.get('mode', 'INBOUND').upper()})


def live_catalogue(request):
    # 1. Security Check
    provided_token = request.GET.get('token')
    if not provided_token:
        return HttpResponseForbidden("Access Denied: Missing reseller token.")

    try:
        reseller = ResellerToken.objects.get(token=provided_token, is_active=True)
    except ResellerToken.DoesNotExist:
        return HttpResponseForbidden("Access Denied: Invalid or revoked link.")

    # 2. Get Filter Parameters (Including Search)
    search_query = request.GET.get('search')
    product_type = request.GET.get('product_type')
    weaver = request.GET.get('weaver')
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')

    # 3. Base Query
    products = FinishedProduct.objects.filter(
        status__in=[InventoryStatus.IN_STOCK, InventoryStatus.RETURNED]
    ).order_by('-date_entered')

    # 4. Apply Global Keyword Search
    if search_query:
        products = products.filter(
            Q(id__icontains=search_query) |
            Q(weaver_name__icontains=search_query) |
            Q(design_work__icontains=search_query) |
            Q(product_type__icontains=search_query)
        )

    # 5. Apply Specific Filters
    if product_type:
        products = products.filter(product_type__icontains=product_type)
    if weaver:
        products = products.filter(weaver_name__icontains=weaver)
    if min_price:
        products = products.filter(price__gte=min_price)
    if max_price:
        products = products.filter(price__lte=max_price)

    context = {
        'products': products,
        'reseller_name': reseller.reseller_name,
        'token': provided_token,
        'search_query': search_query or '',
        'product_type_query': product_type or '',
        'weaver_query': weaver or '',
        'min_price': min_price or '',
        'max_price': max_price or '',
    }

    return render(request, 'catalogue.html', context)


@csrf_exempt
@api_view(['POST'])
@authentication_classes([])
@permission_classes([])
def log_inbound(request):
    qr_id = request.data.get('qr_id')

    # Validation gatekeeper
    if qr_id and not is_valid_qr(qr_id):
        return Response(
            {'error': 'Invalid QR Format. Unrecognized company or area code.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    product_type = request.data.get('product_type')
    raw_price = request.data.get('price')
    price_value = raw_price if raw_price else 0.00

    # NEW: Capture the reused image path from bulk mode
    reused_image_path = request.data.get('reused_image_path')

    if not qr_id or not product_type:
        return Response({'error': 'Missing QR ID or Product Type'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        existing_product = FinishedProduct.objects.filter(id=qr_id).first()
        if existing_product:
            if existing_product.status == InventoryStatus.IN_STOCK:
                return Response({'error': 'Item is already IN_STOCK!'}, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response({'error': 'Item already DISPATCHED. Use the Return tab.'}, status=status.HTTP_400_BAD_REQUEST)

        product = FinishedProduct.objects.create(
            id=qr_id,
            product_type=product_type,
            design_work=request.data.get('design_work', ''),
            weaver_name=request.data.get('weaver_name', ''),
            price=price_value,
            status=InventoryStatus.IN_STOCK,
            date_entered=timezone.now()
        )

        saved_path = ""

        # --- NEW: IMAGE HANDLING LOGIC ---
        if reused_image_path:
            product.product_image.name = reused_image_path
            product.save()
            saved_path = reused_image_path
        elif 'product_image' in request.FILES:
            raw_image = request.FILES['product_image']
            product.product_image = compress_image(raw_image)
            product.save()
            saved_path = product.product_image.name

        return Response({
            'message': f'Item {qr_id} logged successfully!',
            'saved_image_path': saved_path
        })
    except Exception as e:
        return Response({'error': f"Database Error: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


@csrf_exempt
@api_view(['POST'])
@authentication_classes([])
@permission_classes([])
def log_outbound(request):
    qr_id = request.data.get('qr_id')
    pincode = request.data.get('pincode')
    channel = request.data.get('sales_channel')

    if not qr_id:
        return Response({'error': 'Missing QR code'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        product = FinishedProduct.objects.get(id=qr_id)
        if product.status == InventoryStatus.DISPATCHED:
            date_str = product.date_dispatched.strftime("%d-%b-%Y") if product.date_dispatched else "an unknown date"
            return Response({'error': f'Item already marked as DISPATCHED on {date_str}!'}, status=status.HTTP_400_BAD_REQUEST)

    except FinishedProduct.DoesNotExist:
        return Response({'error': 'Item not found! You must log it Inbound first.'}, status=status.HTTP_404_NOT_FOUND)

    state, city = "", ""
    if pincode:
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            resp = requests.get(f'https://api.postalpincode.in/pincode/{pincode}', headers=headers, timeout=5)

            if resp.status_code == 200:
                data = resp.json()[0]
                if data.get('Status') == 'Success':
                    post_office = data['PostOffice'][0]
                    state = post_office.get('State', '')
                    city = post_office.get('District', '')
        except Exception:
            pass

    product.status = InventoryStatus.DISPATCHED
    product.date_dispatched = timezone.now()
    product.pincode = pincode
    product.derived_state = state
    product.derived_city = city
    product.sales_channel = channel
    product.save()

    location_msg = f"{city}, {state}".strip(', ')
    return Response({
        'message': f'Dispatched successfully to {location_msg}' if location_msg else 'Dispatched successfully!'
    })


@csrf_exempt
@api_view(['POST'])
@authentication_classes([])
@permission_classes([])
def log_return(request):

    qr_id = request.data.get('qr_id')
    reason = request.data.get('return_reason', 'OTHER')
    # --- NEW VALIDATION GATEKEEPER ---
    if qr_id and not is_valid_qr(qr_id):
        return Response(
            {'error': 'Invalid QR Format. Unrecognized company or area code.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    product_type = request.data.get('product_type')

    if not qr_id:
        return Response({'error': 'Missing QR code'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        product = FinishedProduct.objects.get(id=qr_id)
        if product.status == InventoryStatus.RETURNED or product.status == InventoryStatus.IN_STOCK:
            return Response({'error': 'Item is already in the warehouse!'}, status=status.HTTP_400_BAD_REQUEST)

        product.status = InventoryStatus.RETURNED
        product.return_reason = reason
        product.save()
        return Response({'message': 'Item marked as RETURNED and placed back in inventory.'})
    except FinishedProduct.DoesNotExist:
        return Response({'error': 'Item not found in system!'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def lookup_product(request):
    """Read-only QR lookup for the scanner's LOOKUP mode and the admin.
    Unlike the three log_* endpoints above, this is a new surface with no
    prior open-API expectation, so it requires the same login the scanner
    page itself now requires (session auth via Django's regular login)."""
    qr_id = (request.GET.get('qr_id') or '').strip()
    if not qr_id:
        return Response({'error': 'Missing QR code'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        product = FinishedProduct.objects.get(id=qr_id)
    except FinishedProduct.DoesNotExist:
        return Response({'error': 'No product found for this QR code'}, status=status.HTTP_404_NOT_FOUND)

    return Response({
        'id': product.id,
        'product_type': product.product_type,
        'design_work': product.design_work or '',
        'weaver_name': product.weaver_name or '',
        'price': str(product.price),
        'status': product.status,
        'status_display': product.get_status_display(),
        'is_dead_stock': product.is_dead_stock,
        'return_reason': product.get_return_reason_display() if product.return_reason else '',
        'date_entered': product.date_entered.strftime('%d %b %Y') if product.date_entered else '',
        'date_dispatched': product.date_dispatched.strftime('%d %b %Y') if product.date_dispatched else '',
        'sales_channel': product.get_sales_channel_display() if product.sales_channel else '',
        'pincode': product.pincode or '',
        'derived_city': product.derived_city or '',
        'derived_state': product.derived_state or '',
        'image_url': product.product_image.url if product.product_image else '',
    })


@login_required(login_url=LOGIN_URL)
def financial_dashboard(request):
    # Calculate Capital on Shelves (IN_STOCK)
    in_stock = FinishedProduct.objects.filter(status=InventoryStatus.IN_STOCK)
    inventory_value = in_stock.aggregate(Sum('price'))['price__sum'] or 0
    stock_count = in_stock.count()

    # Calculate Total Revenue (DISPATCHED)
    dispatched = FinishedProduct.objects.filter(status=InventoryStatus.DISPATCHED)
    total_sales = dispatched.aggregate(Sum('price'))['price__sum'] or 0
    sales_count = dispatched.count()

    dead_stock = FinishedProduct.objects.filter(is_dead_stock=True, status__in=['IN_STOCK', 'RETURNED'])

    context = {
        'inventory_value': inventory_value,
        'stock_count': stock_count,
        'total_sales': total_sales,
        'sales_count': sales_count,
        'dead_stock_count': dead_stock.count(),
        'dead_stock_value': dead_stock.aggregate(Sum('price'))['price__sum'] or 0,
    }
    return render(request, 'dashboard.html', context)


def admin_dashboard_callback(request, context):
    in_stock = FinishedProduct.objects.filter(status=InventoryStatus.IN_STOCK)
    dispatched = FinishedProduct.objects.filter(status=InventoryStatus.DISPATCHED)
    dead_stock = FinishedProduct.objects.filter(is_dead_stock=True, status__in=['IN_STOCK', 'RETURNED'])

    context.update({
        "inventory_value": in_stock.aggregate(Sum('price'))['price__sum'] or 0,
        "stock_count": in_stock.count(),
        "total_sales": dispatched.aggregate(Sum('price'))['price__sum'] or 0,
        "sales_count": dispatched.count(),
        "dead_stock_count": dead_stock.count(),
        "dead_stock_value": dead_stock.aggregate(Sum('price'))['price__sum'] or 0,
    })
    return context


# ---- White-label setup wizard ---------------------------------------------

def _brand_folder():
    return os.path.join(settings.BASE_DIR, 'brand')


def _list_brand_assets():
    """Image files the operator has dropped into the top-level /brand folder,
    offered as one-click logo choices in the setup wizard."""
    folder = _brand_folder()
    if not os.path.isdir(folder):
        return []
    return sorted(
        f for f in os.listdir(folder)
        if f.lower().endswith(BRAND_ASSET_EXTENSIONS)
    )


def serve_brand_asset(request, filename):
    """Serves a single image straight out of /brand, for wizard previews only.
    Restricted to a basename match (no path traversal) and an image extension
    allowlist -- this never serves arbitrary files."""
    safe_name = os.path.basename(filename)
    if safe_name != filename or not safe_name.lower().endswith(BRAND_ASSET_EXTENSIONS):
        raise Http404()
    path = os.path.join(_brand_folder(), safe_name)
    if not os.path.isfile(path):
        raise Http404()
    content_type, _ = mimetypes.guess_type(path)
    return FileResponse(open(path, 'rb'), content_type=content_type or 'application/octet-stream')


def setup_wizard(request):
    """The first-launch 'launch window': pick a brand name, accent color, and
    logo before the rest of the app becomes reachable (see middleware.py)."""
    config = SiteConfig.load()

    if request.method == 'POST':
        config.brand_name = (request.POST.get('brand_name') or '').strip() or 'Textiler'
        config.tagline = (request.POST.get('tagline') or '').strip()
        config.currency_symbol = (request.POST.get('currency_symbol') or '').strip() or '₹'

        accent_hex = (request.POST.get('accent_hex') or '').strip()
        if re.match(r'^#[0-9A-Fa-f]{6}$', accent_hex):
            config.accent_hex = accent_hex

        logo_file = request.FILES.get('logo')
        selected_asset = (request.POST.get('brand_asset') or '').strip()

        if logo_file:
            config.logo = logo_file
        elif selected_asset:
            safe_name = os.path.basename(selected_asset)
            asset_path = os.path.join(_brand_folder(), safe_name)
            if safe_name.lower().endswith(BRAND_ASSET_EXTENSIONS) and os.path.isfile(asset_path):
                with open(asset_path, 'rb') as f:
                    config.logo.save(safe_name, ContentFile(f.read()), save=False)

        config.is_setup_complete = True
        config.save()
        return redirect('scanner_ui')

    context = {
        'config': config,
        'presets': BRAND_PROFILE_PRESETS,
        'brand_assets': _list_brand_assets(),
    }
    return render(request, 'setup_wizard.html', context)


# ---- PWA: manifest + service worker ----------------------------------------

def _icon_meta(image_field):
    url = image_field.url
    if url.lower().endswith('.svg'):
        return {'src': url, 'sizes': 'any', 'type': 'image/svg+xml', 'purpose': 'any'}
    try:
        with Image.open(image_field.path) as img:
            w, h = img.size
        mime = Image.MIME.get(img.format, 'image/png')
    except Exception:
        w, h, mime = 192, 192, 'image/png'
    return {'src': url, 'sizes': f'{w}x{h}', 'type': mime, 'purpose': 'any'}


def pwa_manifest(request):
    config = SiteConfig.load()
    if config.logo:
        icon = _icon_meta(config.logo)
    else:
        icon = {'src': static('tracker/logo-default.svg'), 'sizes': 'any', 'type': 'image/svg+xml', 'purpose': 'any'}

    manifest = {
        "name": config.brand_name,
        "short_name": config.brand_name[:12],
        "description": config.tagline or f"{config.brand_name} warehouse scanner",
        "start_url": "/scanner/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": config.accent_hex,
        "icons": [icon],
    }
    return JsonResponse(manifest, content_type='application/manifest+json')


SERVICE_WORKER_JS = """
const CACHE = 'app-shell-v1';
const SHELL_URLS = ['/scanner/'];

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL_URLS)));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

// Network-first: this app is data-critical (live inventory scans), so it must
// never silently serve a stale cached page. The cache is only an app-shell
// fallback for genuine offline access -- there is no offline scan queue.
self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});
"""


def service_worker(request):
    return HttpResponse(SERVICE_WORKER_JS, content_type='application/javascript')
