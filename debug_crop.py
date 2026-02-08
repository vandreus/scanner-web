"""Debug script to analyze the scanned image and test cropping"""
import os
from PIL import Image
import img2pdf
import io

# Get the most recent scan
scan_dir = "C:/dev/scanner-web/scans/Receipts"
files = sorted([f for f in os.listdir(scan_dir) if f.endswith('.pdf')], reverse=True)
if not files:
    print("No PDFs found")
    exit()

print(f"Latest scan: {files[0]}")

# Let's scan fresh and capture raw image
import requests
import urllib3
urllib3.disable_warnings()

SCANNER_IP = "10.69.7.167"
ESCL_BASE = f"https://{SCANNER_IP}:443/eSCL"

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

print("\nScanning...")
response = requests.post(
    f"{ESCL_BASE}/ScanJobs",
    data=scan_settings,
    headers={"Content-Type": "application/xml"},
    verify=False,
    timeout=30
)
print(f"Create job: {response.status_code}")

job_url = response.headers.get('Location', '')
if not job_url.startswith('http'):
    job_url = f"https://{SCANNER_IP}:443{job_url}"

import time
time.sleep(2)

page_url = f"{job_url}/NextDocument"
print(f"Fetching image...")
page_response = requests.get(page_url, verify=False, timeout=120)
print(f"Got image: {len(page_response.content)} bytes")

# Save raw
raw_path = "C:/dev/scanner-web/test_scans/debug_raw.jpg"
with open(raw_path, 'wb') as f:
    f.write(page_response.content)

img = Image.open(raw_path)
gray = img.convert('L')
pixels = gray.load()
width, height = gray.size

print(f"\n=== IMAGE ANALYSIS ===")
print(f"Size: {width}x{height} pixels")
print(f"Height in inches: {height/300:.1f}")

# Sample various areas
print(f"\n=== PIXEL VALUES ===")
print("Scanner background (gray ~180-195):")
print(f"  Top-left (10,10): {pixels[10,10]}")
print(f"  Top-right ({width-10},10): {pixels[width-10,10]}")
print(f"  Bottom-left (10,{height-10}): {pixels[10,height-10]}")
print(f"  Bottom-right ({width-10},{height-10}): {pixels[width-10,height-10]}")

# Sample down the middle
print(f"\nDown the middle (x={width//2}):")
for y in range(0, height, height//20):
    print(f"  y={y}: {pixels[width//2, y]}")

# Find where paper starts/ends (white pixels >220)
print(f"\n=== FINDING PAPER (pixels > 220) ===")
paper_rows = []
for y in range(0, height, 10):
    white_count = sum(1 for x in range(0, width, 10) if pixels[x, y] > 220)
    if white_count > 5:  # At least 5 white samples in this row
        paper_rows.append(y)

if paper_rows:
    print(f"Paper found from y={paper_rows[0]} to y={paper_rows[-1]}")
    print(f"Paper height: {(paper_rows[-1] - paper_rows[0])/300:.1f} inches")
else:
    print("No paper detected!")

# Find content (pixels < 150)
print(f"\n=== FINDING CONTENT (pixels < 150) ===")
content_min_y, content_max_y = height, 0
for y in range(0, height, 5):
    for x in range(0, width, 5):
        if pixels[x, y] < 150:
            content_min_y = min(content_min_y, y)
            content_max_y = max(content_max_y, y)

if content_max_y > content_min_y:
    print(f"Content found from y={content_min_y} to y={content_max_y}")
    print(f"Content height: {(content_max_y - content_min_y)/300:.1f} inches")
else:
    print("No content detected!")

# Test both thresholds
print(f"\n=== THRESHOLD ANALYSIS ===")
for thresh in [250, 240, 230, 220, 210, 200, 190, 180, 170, 160, 150]:
    min_y, max_y = height, 0
    for y in range(0, height, 10):
        for x in range(0, width, 10):
            if pixels[x, y] < thresh:
                min_y = min(min_y, y)
                max_y = max(max_y, y)
    if max_y > min_y:
        print(f"  Threshold <{thresh}: y={min_y} to y={max_y} ({(max_y-min_y)/300:.1f} inches)")
