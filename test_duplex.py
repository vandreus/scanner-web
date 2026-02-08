"""Test duplex scanning"""
import requests
import urllib3
import time
import os
from PIL import Image
import img2pdf
import io

urllib3.disable_warnings()
Image.MAX_IMAGE_PIXELS = 200000000

SCANNER_IP = "10.69.7.167"
ESCL_BASE = f"https://{SCANNER_IP}:443/eSCL"

# Check capabilities first
print("Checking scanner capabilities for duplex...")
response = requests.get(f"{ESCL_BASE}/ScannerCapabilities", verify=False, timeout=10)
caps = response.text

if "Duplex" in caps:
    print("Scanner supports Duplex!")
    # Find the duplex-related XML
    import re
    duplex_matches = re.findall(r'<[^>]*[Dd]uplex[^>]*>[^<]*</[^>]*>', caps)
    for m in duplex_matches[:10]:
        print(f"  {m}")
else:
    print("No duplex mention found in capabilities")

# Check ADF capabilities
if "Adf" in caps:
    print("\nADF capabilities found")
    adf_section = caps[caps.find("<scan:Adf>"):caps.find("</scan:Adf>")+11] if "<scan:Adf>" in caps else ""
    if "Duplex" in adf_section:
        print("ADF supports duplex")

# Check status
print("\nChecking scanner status...")
response = requests.get(f"{ESCL_BASE}/ScannerStatus", verify=False, timeout=5)
if "ScannerAdfEmpty" in response.text:
    print("ADF is EMPTY - please load a 2-sided document")
    exit()
print("Paper detected")

# Try duplex scan
print("\n" + "="*50)
print("Testing DUPLEX scan")
print("="*50)

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
    <scan:Duplex>true</scan:Duplex>
</scan:ScanSettings>"""

print("\nScan settings:")
print(scan_settings)

print("\nCreating scan job...")
response = requests.post(
    f"{ESCL_BASE}/ScanJobs",
    data=scan_settings,
    headers={"Content-Type": "application/xml"},
    verify=False,
    timeout=30
)
print(f"Response: {response.status_code}")
if response.status_code not in [200, 201]:
    print(f"Error: {response.text[:500]}")
    exit()

job_url = response.headers.get('Location', '')
if not job_url.startswith('http'):
    job_url = f"https://{SCANNER_IP}:443{job_url}"
print(f"Job URL: {job_url}")

time.sleep(3)

# Fetch pages
images = []
page_num = 1
while page_num <= 10:
    page_url = f"{job_url}/NextDocument"
    print(f"\nFetching page {page_num}...")

    response = requests.get(page_url, verify=False, timeout=120)
    print(f"Response: {response.status_code}, {len(response.content)} bytes")

    if response.status_code == 200 and len(response.content) > 1000:
        img = Image.open(io.BytesIO(response.content))
        print(f"Page {page_num}: {img.size[0]}x{img.size[1]}")
        images.append(img)
        page_num += 1
        time.sleep(0.5)
    elif response.status_code == 404:
        print("No more pages")
        break
    else:
        print(f"Unexpected response: {response.text[:200]}")
        break

print(f"\n{'='*50}")
print(f"Got {len(images)} page(s)")
print("="*50)

if images:
    for i, img in enumerate(images):
        path = f"C:/dev/scanner-web/test_scans/duplex_page_{i+1}.jpg"
        img.save(path, quality=90)
        print(f"Saved: {path}")
