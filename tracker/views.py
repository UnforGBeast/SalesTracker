from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
import requests
from .models import FinishedProduct, InventoryStatus

def scanner_ui(request):
    return render(request, 'scanner.html')

@csrf_exempt
@api_view(['POST'])
def log_inbound(request):
    qr_id = request.data.get('qr_id')
    product_type = request.data.get('product_type')
    
    if not qr_id or not product_type:
        return Response({'error': 'Missing QR ID or Product Type'}, status=status.HTTP_400_BAD_REQUEST)
        
    try:
        # Prevent duplicate inbound scanning
        existing_product = FinishedProduct.objects.filter(id=qr_id).first()
        if existing_product:
            if existing_product.status == InventoryStatus.IN_STOCK:
                return Response({'error': 'This item is already logged IN_STOCK!'}, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response({'error': 'This item has already been DISPATCHED and cannot be logged inbound again.'}, status=status.HTTP_400_BAD_REQUEST)

        # Create new entry
        FinishedProduct.objects.create(
            id=qr_id,
            product_type=product_type,
            design_work=request.data.get('design_work', ''),
            weaver_name=request.data.get('weaver_name', ''),
            status=InventoryStatus.IN_STOCK,
            date_entered=timezone.now()
        )
        return Response({'message': 'Item logged into inventory successfully!'})
    except Exception as e:
        return Response({'error': f"Database Error: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


@csrf_exempt
@api_view(['POST'])
def log_outbound(request):
    qr_id = request.data.get('qr_id')
    pincode = request.data.get('pincode')
    channel = request.data.get('sales_channel')
    
    if not qr_id:
        return Response({'error': 'Missing QR code'}, status=status.HTTP_400_BAD_REQUEST)
        
    try:
        product = FinishedProduct.objects.get(id=qr_id)
        
        # Prevent double dispatching
        if product.status == InventoryStatus.DISPATCHED:
            date_str = product.date_dispatched.strftime("%d-%b-%Y") if product.date_dispatched else "an unknown date"
            return Response({'error': f'Item already marked as DISPATCHED on {date_str}!'}, status=status.HTTP_400_BAD_REQUEST)
            
    except FinishedProduct.DoesNotExist:
        return Response({'error': 'Item not found! You must log it Inbound first.'}, status=status.HTTP_404_NOT_FOUND)
        
    state, city = "", ""
    if pincode:
        try:
            # Bypass anti-bot filters with a User-Agent header
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            resp = requests.get(f'https://api.postalpincode.in/pincode/{pincode}', headers=headers, timeout=5)
            
            if resp.status_code == 200:
                data = resp.json()[0]
                if data.get('Status') == 'Success':
                    post_office = data['PostOffice'][0]
                    state = post_office.get('State', '')
                    city = post_office.get('District', '')
        except Exception:
            pass # Fail silently if API goes down so it doesn't block the dispatch
            
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