import os
import urllib.request
import re
from pathlib import Path

# Base directories
BASE_DIR = Path(r"d:\ODtech\Main_work\Deployment\ODtech")
STATIC_VENDOR_DIR = BASE_DIR / "static" / "vendor"
JS_DIR = STATIC_VENDOR_DIR / "js"
CSS_DIR = STATIC_VENDOR_DIR / "css"
FONTS_DIR = STATIC_VENDOR_DIR / "fonts"
TEMPLATES_DIR = BASE_DIR / "templates"

# Create directories
for d in [JS_DIR, CSS_DIR, FONTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# List of JS files to download and their regex in HTML
ASSETS = [
    ("https://cdn.tailwindcss.com", "tailwindcss.js"),
    ("https://cdn.jsdelivr.net/npm/@alpinejs/collapse@3.x.x/dist/cdn.min.js", "alpine-collapse.min.js"),
    ("https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js", "alpine.min.js"),
    ("https://cdn.jsdelivr.net/npm/sortablejs@1.15.2/Sortable.min.js", "Sortable.min.js"),
    ("https://unpkg.com/htmx.org@1.9.10", "htmx.min.js"),
    ("https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js", "xlsx.full.min.js"),
    ("https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js", "jspdf.umd.min.js"),
    ("https://cdnjs.cloudflare.com/ajax/libs/jspdf-autotable/3.5.28/jspdf.plugin.autotable.min.js", "jspdf.plugin.autotable.min.js"),
    ("https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js", "html2canvas.min.js"),
    ("https://cdn.jsdelivr.net/npm/qrcodejs@1.0.0/qrcode.min.js", "qrcode.min.js"),
    ("https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.min.js", "jsQR.min.js"),
    ("https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js", "chart.umd.min.js"),
    ("https://cdn.jsdelivr.net/npm/apexcharts", "apexcharts.js"),
]

def download_file(url, filepath):
    if not filepath.exists():
        print(f"Downloading {url}...")
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                filepath.write_bytes(response.read())
            print(f"Saved to {filepath}")
        except Exception as e:
            print(f"Failed to download {url}: {e}")
    else:
        print(f"Already exists: {filepath}")

# Download JS Assets
print("--- Downloading JS Assets ---")
for url, filename in ASSETS:
    download_file(url, JS_DIR / filename)

# Handle Google Fonts
print("\n--- Downloading Google Fonts ---")
FONT_API_URL = "https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap"
try:
    req = urllib.request.Request(FONT_API_URL, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36'})
    with urllib.request.urlopen(req) as response:
        css_content = response.read().decode('utf-8')
    
    # Find all url(...) in CSS
    urls = re.findall(r'url\((https://[^)]+\.woff2)\)', css_content)
    
    for woff2_url in set(urls):
        font_filename = woff2_url.split('/')[-1]
        font_path = FONTS_DIR / font_filename
        download_file(woff2_url, font_path)
        
        # Replace the URL in the CSS
        css_content = css_content.replace(woff2_url, f'../fonts/{font_filename}')
    
    css_path = CSS_DIR / "fonts.css"
    css_path.write_text(css_content, encoding='utf-8')
    print("Google Fonts CSS saved and updated.")
except Exception as e:
    print(f"Error handling Google Fonts: {e}")


# Update Templates
print("\n--- Updating HTML Templates ---")
font_regex = re.compile(r'https://fonts\.googleapis\.com/css2\?family=Outfit[^"]*')

for root, dirs, files in os.walk(TEMPLATES_DIR):
    for file in files:
        if file.endswith('.html'):
            filepath = Path(root) / file
            try:
                content = filepath.read_text(encoding='utf-8')
                original_content = content
                
                # Replace Font Link
                content = font_regex.sub("{% static 'vendor/css/fonts.css' %}", content)
                
                # Replace JS Links
                for url, filename in ASSETS:
                    content = content.replace(url, f"{{% static 'vendor/js/{filename}' %}}")
                
                if content != original_content:
                    # Check if {% load static %} exists at top
                    if "{% load static %}" not in content:
                        if "{% extends" in content:
                            content = re.sub(r'({% extends[^%]+%})\s*', r'\1\n{% load static %}\n', content, count=1)
                        else:
                            content = "{% load static %}\n" + content
                    
                    filepath.write_text(content, encoding='utf-8')
                    print(f"Updated: {filepath.relative_to(BASE_DIR)}")
            except Exception as e:
                print(f"Failed to update {filepath.relative_to(BASE_DIR)}: {e}")

print("\n--- DONE! All assets localized. ---")
