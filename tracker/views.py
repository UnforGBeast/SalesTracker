from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
import requests
from .models import FinishedProduct, InventoryStatus
from django.shortcuts import render

@api_view(['POST'])
def log_inbound(request):
    """ Logs a new item to the shelf """
    qr_id = request.data.get('qr_id')
    product_type = request.data.get('product_type')
    
    if not qr_id or not product_type:
        return Response({'error': 'Missing QR ID or Product Type'}, status=status.HTTP_400_BAD_REQUEST)
        
    # Get the pre-printed QR code row, or create it if testing manually
    product, created = FinishedProduct.objects.get_or_create(id=qr_id)
    product.product_type = product_type
    product.design_work = request.data.get('design_work', '')
    product.weaver_name = request.data.get('weaver_name', '')
    product.status = InventoryStatus.IN_STOCK
    product.date_entered = timezone.now()
    product.save()
    
    return Response({'message': 'Item logged into inventory successfully!'})

@api_view(['POST'])
def log_outbound(request):
    """ Logs an item out of the warehouse and fetches location data """
    qr_id = request.data.get('qr_id')
    pincode = request.data.get('pincode')
    channel = request.data.get('sales_channel')
    
    if not qr_id:
        return Response({'error': 'Missing QR code'}, status=status.HTTP_400_BAD_REQUEST)
        
    try:
        product = FinishedProduct.objects.get(id=qr_id)
    except FinishedProduct.DoesNotExist:
        return Response({'error': 'Item not found in inventory'}, status=status.HTTP_404_NOT_FOUND)
        
    state, city = "", ""
    if pincode:
        # Free Indian Pincode API lookup
        try:
            resp = requests.get(f'https://api.postalpincode.in/pincode/{pincode}', timeout=3)
            if resp.status_code == 200 and resp.json()[0]['Status'] == 'Success':
                post_office = resp.json()[0]['PostOffice'][0]
                state = post_office['State']
                city = post_office['District']
        except requests.exceptions.RequestException:
            pass # Fail silently if the post office API goes down, just log the pincode
            
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
def scanner_ui(request):
    """ Serves the mobile HTML scanner interface """
    return render(request, 'scanner.html')