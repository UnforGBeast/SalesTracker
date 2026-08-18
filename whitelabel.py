#!/usr/bin/env python3
import os
import subprocess
import re
import shutil

ENV_PATH = ".env"
# Define where the script should copy the uploaded logos
MEDIA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media", "branding")

COLOR_OPTIONS = {
    "1": ("Slate / Neutral Dark", "slate"),
    "2": ("Royal Indigo", "indigo"),
    "3": ("Emerald Green", "emerald"),
    "4": ("Rose / Crimson", "rose"),
    "5": ("Amber / Gold", "amber"),
    "6": ("Sky Blue", "sky"),
}

def update_env_file(key, value):
    """Updates or adds an environment variable in the .env file."""
    if not os.path.exists(ENV_PATH):
        with open(ENV_PATH, "w") as f:
            f.write(f"{key}={value}\n")
        return

    with open(ENV_PATH, "r") as f:
        content = f.read()

    pattern = rf"^{key}=.*$"
    replacement = f"{key}='{value}'"

    if re.search(pattern, content, flags=re.MULTILINE):
        content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
    else:
        content += f"\n{replacement}"

    with open(ENV_PATH, "w") as f:
        f.write(content.strip() + "\n")

def process_logo():
    """Handles the logo copying process."""
    logo_path = input("\n🖼️ Enter the path to the client's logo file (or press Enter to skip): ").strip()
    
    if not logo_path:
        return None

    if not os.path.exists(logo_path):
        print("⚠ Error: File not found at that path. Skipping logo upload.")
        return None

    # Ensure the branding media directory exists
    os.makedirs(MEDIA_DIR, exist_ok=True)
    
    # Get file extension and create a standardized filename
    _, ext = os.path.splitext(logo_path)
    new_filename = f"client_logo{ext.lower()}"
    destination = os.path.join(MEDIA_DIR, new_filename)

    try:
        shutil.copy2(logo_path, destination)
        # Return the public URL path that Django will use
        return f"/media/branding/{new_filename}"
    except Exception as e:
        print(f"⚠ Error copying logo: {e}")
        return None

def main():
    print("=" * 50)
    print("      WHITE-LABEL INSTANCE CUSTOMIZATION WIZARD   ")
    print("=" * 50)

    # 1. Company Name
    brand_name = input("\n👉 Enter Client Company Name (e.g. 'Royal Banaras'): ").strip()
    if not brand_name:
        brand_name = "Silk O Zari"

    # 2. Currency Symbol
    currency_symbol = input("👉 Enter Currency Symbol [Default: ₹]: ").strip()
    if not currency_symbol:
        currency_symbol = "₹"

    # 3. Theme Color
    print("\n🎨 Select a Primary Brand Accent Color:")
    for num, (name, _) in COLOR_OPTIONS.items():
        print(f"  [{num}] {name}")
    choice = input("Select (1-6) [Default: 1]: ").strip()
    selected_color = COLOR_OPTIONS.get(choice, ("Slate", "slate"))[1]

    # 4. Logo Upload
    logo_url = process_logo()

    # Save to .env
    update_env_file("BRAND_NAME", brand_name)
    update_env_file("BRAND_COLOR", selected_color)
    update_env_file("CURRENCY_SYMBOL", currency_symbol)
    
    if logo_url:
        update_env_file("BRAND_LOGO", logo_url)

    print("\n" + "-" * 50)
    print(f"✔ Configuration Saved to .env:")
    print(f"   • Company Name:    {brand_name}")
    print(f"   • Primary Palette: {selected_color}")
    print(f"   • Currency:        {currency_symbol}")
    if logo_url:
        print(f"   • Logo Path:       {logo_url}")
    print("-" * 50)

    # Restart Gunicorn service
    restart = input("\n🔄 Restart Gunicorn now to apply changes? (y/n) [y]: ").strip().lower()
    if restart != 'n':
        try:
            subprocess.run(["sudo", "systemctl", "restart", "gunicorn"], check=True)
            print("✔ Gunicorn restarted successfully! Changes are live.")
        except Exception as e:
            print(f"⚠ Could not restart Gunicorn automatically: {e}")

if __name__ == "__main__":
    main()