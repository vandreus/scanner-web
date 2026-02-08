"""Test scanning a long document (8.5x14) with detailed analysis"""
import requests
import urllib3
import time
import os
from PIL import Image
import img2pdf
import io

urllib3.disable_warnings()

SCANNER_IP = "10.69.7.167"
ESCL_BASE = f"https://{SCANNER_IP}:443/eSCL"

# First check if paper is loaded
print("Checking scanner status...")
response = requests.get(f"{ESCL_BASE}/ScannerStatus", verify=False, timeout=5)
if "ScannerAdfEmpty" in response.text:
    print("\n*** ADF is EMPTY - Please load your 8.5x14 document and run again ***")
    exit()
elif "ScannerAdfLoaded" in response.text:
    print("Paper detected in ADF - proceeding with scan")
else:
    print(f"Unknown ADF state, proceeding anyway...")

# Scan with max height
scan_settings = """<?xml version="1.0" encoding="UTF-8"?>
<scan:ScanSettings xmlns:scan="http://schemas.hp.com/imaging/escl/2011/05/03"
                   xmlns:pwg="http://www.pwg.org/schemas/2010/12/sm">
    <pwg:Version>2.63</pwg:Version>
    <scan:Intent>Document</scan:Intent>
    <pwg:ScanRegions>
        <pwg:ScanRegion>
            <pwg:Height>36600</pwg:Height>
            <pwg:Width>2550</pwg:Width>
            <pwg:XOffset>0</pwg:XOffset>
            <pwg:YOffset>0</pwg:YOffset>
        </pwg:ScanRegion>
    </pwg:ScanRegions>
    <pwg:InputSource>Feeder</pwg:InputSource>
    <scan:XResolution>300</scan:XResolution>
    <scan:YResolution>300</scan:YResolution>
    <scan:ColorMode>RGB24</scan:ColorMode>
    <pwg:DocumentFormat>image/jpeg</pwg:DocumentFormat>
    <scan:Duplex>false</scan:Duplex>
</scan:ScanSettings>"""

print("\nStarting scan...")
response = requests.post(
    f"{ESCL_BASE}/ScanJobs",
    data=scan_settings,
    headers={"Content-Type": "application/xml"},
    verify=False,
    timeout=30
)
print(f"Create job: {response.status_code}")

if response.status_code not in [200, 201]:
    print(f"Error: {response.text}")
    exit()

job_url = response.headers.get('Location', '')
if not job_url.startswith('http'):
    job_url = f"https://{SCANNER_IP}:443{job_url}"

print(f"Job URL: {job_url}")

time.sleep(3)  # Wait for scan

page_url = f"{job_url}/NextDocument"
print(f"\nFetching scanned image...")
page_response = requests.get(page_url, verify=False, timeout=120)
print(f"Response: {page_response.status_code}, {len(page_response.content)} bytes")

if page_response.status_code != 200 or len(page_response.content) < 1000:
    print("Failed to get image")
    exit()

# Save raw
raw_path = "C:/dev/scanner-web/test_scans/long_doc_raw.jpg"
os.makedirs(os.path.dirname(raw_path), exist_ok=True)
with open(raw_path, 'wb') as f:
    f.write(page_response.content)
print(f"Saved raw: {raw_path}")

# Analyze
img = Image.open(raw_path)
gray = img.convert('L')
pixels = gray.load()
width, height = gray.size

print(f"\n{'='*50}")
print(f"IMAGE ANALYSIS")
print(f"{'='*50}")
print(f"Size: {width}x{height} pixels")
print(f"Dimensions: {width/300:.1f} x {height/300:.1f} inches")

# Pixel sampling
print(f"\nCorner pixels:")
print(f"  Top-left: {pixels[10,10]}")
print(f"  Top-right: {pixels[width-10,10]}")
print(f"  Bottom-left: {pixels[10,height-10]}")
print(f"  Bottom-right: {pixels[width-10,height-10]}")

# Find paper bounds (white >220)
print(f"\nFinding WHITE PAPER (pixels > 220)...")
paper_min_x, paper_min_y = width, height
paper_max_x, paper_max_y = 0, 0

for y in range(0, height, 5):
    for x in range(0, width, 5):
        if pixels[x, y] > 220:
            paper_min_x = min(paper_min_x, x)
            paper_max_x = max(paper_max_x, x)
            paper_min_y = min(paper_min_y, y)
            paper_max_y = max(paper_max_y, y)

if paper_max_y > paper_min_y:
    print(f"  Paper bounds: ({paper_min_x},{paper_min_y}) to ({paper_max_x},{paper_max_y})")
    print(f"  Paper size: {(paper_max_x-paper_min_x)/300:.1f} x {(paper_max_y-paper_min_y)/300:.1f} inches")
else:
    print("  No white paper detected!")

# Find content bounds (dark <150)
print(f"\nFinding DARK CONTENT (pixels < 150)...")
content_min_x, content_min_y = width, height
content_max_x, content_max_y = 0, 0

for y in range(0, height, 3):
    for x in range(0, width, 3):
        if pixels[x, y] < 150:
            content_min_x = min(content_min_x, x)
            content_max_x = max(content_max_x, x)
            content_min_y = min(content_min_y, y)
            content_max_y = max(content_max_y, y)

if content_max_y > content_min_y:
    print(f"  Content bounds: ({content_min_x},{content_min_y}) to ({content_max_x},{content_max_y})")
    print(f"  Content size: {(content_max_x-content_min_x)/300:.1f} x {(content_max_y-content_min_y)/300:.1f} inches")
else:
    print("  No dark content detected!")

# Determine best crop
print(f"\n{'='*50}")
print(f"AUTO-CROP DECISION")
print(f"{'='*50}")

if content_max_y > content_min_y:
    crop_box = (content_min_x - 30, content_min_y - 30, content_max_x + 30, content_max_y + 30)
    crop_box = (max(0, crop_box[0]), max(0, crop_box[1]), min(width, crop_box[2]), min(height, crop_box[3]))
    print(f"Using CONTENT bounds: {crop_box}")
elif paper_max_y > paper_min_y:
    crop_box = (paper_min_x - 30, paper_min_y - 30, paper_max_x + 30, paper_max_y + 30)
    crop_box = (max(0, crop_box[0]), max(0, crop_box[1]), min(width, crop_box[2]), min(height, crop_box[3]))
    print(f"Using PAPER bounds: {crop_box}")
else:
    print("No bounds found - would keep original")
    crop_box = None

if crop_box:
    cropped = img.crop(crop_box)
    print(f"Cropped size: {cropped.size[0]}x{cropped.size[1]} pixels")
    print(f"Cropped dimensions: {cropped.size[0]/300:.1f} x {cropped.size[1]/300:.1f} inches")

    # Save cropped
    cropped_path = "C:/dev/scanner-web/test_scans/long_doc_cropped.jpg"
    cropped.save(cropped_path, quality=90)
    print(f"\nSaved cropped: {cropped_path}")

    # Save as PDF
    pdf_path = "C:/dev/scanner-web/test_scans/long_doc_cropped.pdf"
    if cropped.mode != 'RGB':
        cropped = cropped.convert('RGB')
    buf = io.BytesIO()
    cropped.save(buf, format='JPEG', quality=90)
    pdf_bytes = img2pdf.convert([buf.getvalue()])
    with open(pdf_path, 'wb') as f:
        f.write(pdf_bytes)
    print(f"Saved PDF: {pdf_path}")
    print(f"PDF size: {os.path.getsize(pdf_path)/1024:.1f} KB")
