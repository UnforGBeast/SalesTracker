from django.shortcuts import render
from rest_framework.decorators import api_view,authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework import status
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
import requests
from .models import FinishedProduct, InventoryStatus
from django.db.models import Sum
from django.db.models import Sum, Q
import re
# --- NEW IMPORTS FOR COMPRESSION ---
from PIL import Image
import io
import sys
from django.core.files.uploadedfile import InMemoryUploadedFile
#links to inventory_list.html and sends the data from the database
from django.shortcuts import render
from django.db.models import Sum, Q
from .models import FinishedProduct

def inventory_list_view(request):
    # 1. Get ALL filter values from the URL
    status_filter = request.GET.get('status')
    search_query = request.GET.get('search')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    pincode = request.GET.get('pincode')
    
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

    # ---------------------------------------------------------
    # NEW: Intercept for CSV Export
    # ---------------------------------------------------------
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="inventory_report.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Barcode ID', 'Product Type', 'Design Work', 'Weaver', 
            'Price', 'Current Status', 'Date Entered', 'Date Dispatched', 
            'Sales Channel', 'Destination Pincode', 'Destination City', 'Destination State'
        ])
        
        for obj in products:
            writer.writerow([
                obj.id, obj.product_type, obj.design_work, obj.weaver_name, 
                obj.price, obj.status, 
                obj.date_entered.strftime('%Y-%m-%d') if obj.date_entered else '', 
                obj.date_dispatched.strftime('%Y-%m-%d') if obj.date_dispatched else '', 
                obj.sales_channel, obj.pincode, obj.derived_city, obj.derived_state
            ])
        return response
    # ---------------------------------------------------------

    # 4. Calculate global dashboard metrics
    global_stock = FinishedProduct.objects.all()
    in_stock = global_stock.filter(status__in=['IN_STOCK', 'RETURNED'])
    dispatched = global_stock.filter(status='DISPATCHED')
    
    inventory_value = in_stock.aggregate(Sum('price'))['price__sum'] or 0
    total_sales = dispatched.aggregate(Sum('price'))['price__sum'] or 0
    
    # 5. Pass everything back to the template
    context = {
        'products': products,
        'inventory_value': inventory_value,
        'stock_count': in_stock.count(),
        'total_sales': total_sales,
        'sales_count': dispatched.count(),
        'current_status': status_filter,
        'search_query': search_query or '',
        'start_date': start_date or '',
        'end_date': end_date or '',
        'min_price': min_price or '',
        'max_price': max_price or '',
        'pincode': pincode or '',
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

def scanner_ui(request):
    return render(request, 'scanner.html')
def live_catalogue(request):
    # Fetch only products sitting in the warehouse, newest first
    available_products = FinishedProduct.objects.filter(
        status__in=[InventoryStatus.IN_STOCK, InventoryStatus.RETURNED]
    ).order_by('-date_entered')
    
    return render(request, 'catalogue.html', {'products': available_products})
@csrf_exempt
@api_view(['POST'])
@authentication_classes([])
@permission_classes([])
def log_inbound(request):
    qr_id = request.data.get('qr_id')
    
    # --- NEW VALIDATION GATEKEEPER ---
    if qr_id and not is_valid_qr(qr_id):
        return Response(
            {'error': 'Invalid QR Format. Unrecognized company or area code.'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    product_type = request.data.get('product_type') 
    raw_price = request.data.get('price')
    price_value = raw_price if raw_price else 0.00
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
        
        # --- COMPRESS BEFORE SAVING ---
        if 'product_image' in request.FILES:
            raw_image = request.FILES['product_image']
            product.product_image = compress_image(raw_image)
            product.save()
            
        return Response({'message': 'Item and image logged successfully!'})
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
def financial_dashboard(request):
    # Calculate Capital on Shelves (IN_STOCK)
    in_stock = FinishedProduct.objects.filter(status=InventoryStatus.IN_STOCK)
    inventory_value = in_stock.aggregate(Sum('price'))['price__sum'] or 0
    stock_count = in_stock.count()

    # Calculate Total Revenue (DISPATCHED)
    dispatched = FinishedProduct.objects.filter(status=InventoryStatus.DISPATCHED)
    total_sales = dispatched.aggregate(Sum('price'))['price__sum'] or 0
    sales_count = dispatched.count()

    context = {
        'inventory_value': inventory_value,
        'stock_count': stock_count,
        'total_sales': total_sales,
        'sales_count': sales_count,
    }
    return render(request, 'dashboard.html', context)
def admin_dashboard_callback(request, context):
    in_stock = FinishedProduct.objects.filter(status=InventoryStatus.IN_STOCK)
    dispatched = FinishedProduct.objects.filter(status=InventoryStatus.DISPATCHED)

    context.update({
        "inventory_value": in_stock.aggregate(Sum('price'))['price__sum'] or 0,
        "stock_count": in_stock.count(),
        "total_sales": dispatched.aggregate(Sum('price'))['price__sum'] or 0,
        "sales_count": dispatched.count(),
    })
    return context