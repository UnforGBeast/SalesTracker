import qrcode
import random
import string
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Dynamically fetch the codes, stripping away any accidental quotes
COMPANY_CODE = os.getenv('COMPANY_CODE', 'ZOR').replace("'", "").replace('"', "").strip()
AREA_CODE = os.getenv('AREA_CODE', 'LKO').replace("'", "").replace('"', "").strip()

def generate_noise(length=4):
    """Generates random alphanumeric noise."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def create_batch_qrs(product_prefix="TX", batch_size=10):
    # Create the output directory
    os.makedirs('generated_qrs', exist_ok=True)
    
    print(f"Initializing QR Generation for {COMPANY_CODE} (Region: {AREA_CODE})...")
    
    for i in range(batch_size):
        # Construct the deterministic payload
        product_code = f"{product_prefix}{generate_noise()}"
        qr_data = f"{COMPANY_CODE}-{AREA_CODE}-{product_code}"
        
        # Generate the Image
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        filename = f"generated_qrs/{qr_data}.png"
        img.save(filename)
        
        print(f"✅ Generated: {qr_data}")

if __name__ == "__main__":
    # Generate 5 sample tags 
    create_batch_qrs(product_prefix="TX", batch_size=5)