"""Test duplex with more waiting and retries"""
import requests
import urllib3
import time
import io
from PIL import Image

urllib3.disable_warnings()
Image.MAX_IMAGE_PIXELS = 200000000

SCANNER_IP = "10.69.7.167"
ESCL_BASE = f"https://{SCANNER_IP}:443/eSCL"

# Check status
print("Checking scanner status...")
response = requests.get(f"{ESCL_BASE}/ScannerStatus", verify=False, timeout=5)
if "ScannerAdfEmpty" in response.text:
    print("ADF is EMPTY - please load a 2-sided document")
    exit()
print("Paper detected")

# Duplex scan
scan_settings = """<?xml version="1.0" encoding="UTF-8"?>
<scan:ScanSettings xmlns:scan="http://schemas.hp.com/imaging/escl/2011/05/03"
                   xmlns:pwg="http://www.pwg.org/schemas/2010/12/sm">
    <pwg:Version>2.63</pwg:Version>
    <scan:Intent>Document</scan:Intent>
    <pwg:ScanRegions>
        <pwg:ScanRegion>
            <pwg:Height>4200</pwg:Height>
            <pwg:Width>2550</pwg:Width>
            <pwg:XOffset>0</pwg:XOffset>
            <pwg:YOffset>0</pwg:YOffset>
        </pwg:ScanRegion>
    </pwg:ScanRegions>
    <pwg:InputSource>Feeder</pwg:InputSource>
    <scan:AdfOptions><scan:AdfOption>Duplex</scan:AdfOption></scan:AdfOptions>
    <scan:XResolution>300</scan:XResolution>
    <scan:YResolution>300</scan:YResolution>
    <scan:ColorMode>RGB24</scan:ColorMode>
    <pwg:DocumentFormat>image/jpeg</pwg:DocumentFormat>
</scan:ScanSettings>"""

print("\nStarting DUPLEX scan...")
response = requests.post(
    f"{ESCL_BASE}/ScanJobs",
    data=scan_settings,
    headers={"Content-Type": "application/xml"},
    verify=False,
    timeout=30
)
print(f"Create job: {response.status_code}")

if response.status_code not in [200, 201]:
    print(f"Error: {response.text[:500]}")
    exit()

job_url = response.headers.get('Location', '')
if not job_url.startswith('http'):
    job_url = f"https://{SCANNER_IP}:443{job_url}"
print(f"Job: {job_url}")

print("\nWaiting 5 seconds for scanner to process both sides...")
time.sleep(5)

# Check job status
print("\nChecking job status...")
job_status = requests.get(f"{job_url}", verify=False, timeout=10)
print(f"Job status response: {job_status.status_code}")
if job_status.status_code == 200:
    print(f"Status: {job_status.text[:500]}")

# Fetch pages with retries
images = []
page_num = 1
retries = 0
max_retries = 3

while page_num <= 20:
    page_url = f"{job_url}/NextDocument"
    print(f"\nFetching page {page_num}...")

    response = requests.get(page_url, verify=False, timeout=120)
    print(f"Response: {response.status_code}, {len(response.content)} bytes")

    if response.status_code == 200 and len(response.content) > 1000:
        img = Image.open(io.BytesIO(response.content))
        print(f"Page {page_num}: {img.size[0]}x{img.size[1]}")
        images.append(img)
        page_num += 1
        retries = 0
        time.sleep(1)
    elif response.status_code == 404:
        if retries < max_retries:
            print(f"404 - waiting and retrying ({retries+1}/{max_retries})...")
            time.sleep(2)
            retries += 1
        else:
            print("No more pages after retries")
            break
    elif response.status_code == 503:
        print("503 Service Unavailable - scanner busy, waiting...")
        time.sleep(3)
    else:
        print(f"Unexpected: {response.status_code}")
        break

print(f"\n{'='*50}")
print(f"Got {len(images)} page(s)")
print("="*50)

for i, img in enumerate(images):
    path = f"C:/dev/scanner-web/test_scans/duplex_test_p{i+1}.jpg"
    img.save(path, quality=90)
    print(f"Saved: {path}")
