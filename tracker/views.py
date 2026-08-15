from django.shortcuts import render
from rest_framework.decorators import api_view,authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework import status
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
import requests
from .models import FinishedProduct, InventoryStatus

# --- NEW IMPORTS FOR COMPRESSION ---
from PIL import Image
import io
import sys
from django.core.files.uploadedfile import InMemoryUploadedFile

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

@csrf_exempt
@api_view(['POST'])
@authentication_classes([])
@permission_classes([])
def log_inbound(request):
    qr_id = request.data.get('qr_id')
    product_type = request.data.get('product_type')
    
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
    if not qr_id:
        return Response({'error': 'Missing QR code'}, status=status.HTTP_400_BAD_REQUEST)
        
    try:
        product = FinishedProduct.objects.get(id=qr_id)
        if product.status == InventoryStatus.RETURNED or product.status == InventoryStatus.IN_STOCK:
            return Response({'error': 'Item is already in the warehouse!'}, status=status.HTTP_400_BAD_REQUEST)
            
        product.status = InventoryStatus.RETURNED
        product.save()
        return Response({'message': 'Item marked as RETURNED and placed back in inventory.'})
    except FinishedProduct.DoesNotExist:
        return Response({'error': 'Item not found in system!'}, status=status.HTTP_404_NOT_FOUND)