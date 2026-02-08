"""
Analyze the scanned image to understand pixel values for better cropping
"""
from PIL import Image
import os

# Find the most recent scan
scan_dir = "C:/dev/scanner-web/test_scans"
files = [f for f in os.listdir(scan_dir) if f.endswith('.pdf')]
if not files:
    print("No scans found")
    exit()

# We need the raw JPEG, let's scan one and save raw
import requests
import urllib3
urllib3.disable_warnings()

SCANNER_IP = "10.69.7.167"
ESCL_BASE = f"https://{SCANNER_IP}:443/eSCL"

# Get scanner status
response = requests.get(f"{ESCL_BASE}/ScannerStatus", verify=False, timeout=5)
print(f"Scanner status: {response.status_code}")

# Quick scan to get raw image
scan_settings = """<?xml version="1.0" encoding="UTF-8"?>
<scan:ScanSettings xmlns:scan="http://schemas.hp.com/imaging/escl/2011/05/03"
                   xmlns:pwg="http://www.pwg.org/schemas/2010/12/sm">
    <pwg:Version>2.63</pwg:Version>
    <scan:Intent>Document</scan:Intent>
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

job_url = response.headers.get('Location', '')
if not job_url.startswith('http'):
    job_url = f"https://{SCANNER_IP}:443{job_url}"

import time
time.sleep(2)

page_url = f"{job_url}/NextDocument"
print(f"Fetching from {page_url}")
page_response = requests.get(page_url, verify=False, timeout=60)
print(f"Got image: {len(page_response.content)} bytes")

# Save raw JPEG
raw_path = "C:/dev/scanner-web/test_scans/raw_scan.jpg"
with open(raw_path, 'wb') as f:
    f.write(page_response.content)
print(f"Saved raw image to: {raw_path}")

# Analyze it
img = Image.open(raw_path)
gray = img.convert('L')
pixels = gray.load()
width, height = gray.size

print(f"\nImage size: {width}x{height}")

# Sample corners and edges to understand background vs content
print("\nPixel analysis:")
print(f"  Top-left corner (0,0): {pixels[0,0]}")
print(f"  Top-right corner ({width-1},0): {pixels[width-1,0]}")
print(f"  Bottom-left corner (0,{height-1}): {pixels[0,height-1]}")
print(f"  Bottom-right corner ({width-1},{height-1}): {pixels[width-1,height-1]}")
print(f"  Center ({width//2},{height//2}): {pixels[width//2,height//2]}")

# Sample along edges
print("\nLeft edge (x=10):")
for y in range(0, height, height//10):
    print(f"  y={y}: {pixels[10, y]}")

print("\nRight edge (x={width-10}):")
for y in range(0, height, height//10):
    print(f"  y={y}: {pixels[width-10, y]}")

print("\nTop edge (y=10):")
for x in range(0, width, width//10):
    print(f"  x={x}: {pixels[x, 10]}")

# Find actual content bounds using different thresholds
print("\n\nTesting different thresholds:")
for thresh in [250, 240, 230, 220, 200, 180, 150]:
    min_x, min_y = width, height
    max_x, max_y = 0, 0

    for y in range(0, height, 5):
        for x in range(0, width, 5):
            if pixels[x, y] < thresh:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)

    if max_x > min_x:
        crop_w = max_x - min_x
        crop_h = max_y - min_y
        print(f"  Threshold {thresh}: ({min_x},{min_y}) to ({max_x},{max_y}) = {crop_w}x{crop_h}")
