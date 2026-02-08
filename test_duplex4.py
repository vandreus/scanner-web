"""Test duplex - check if both sides come as separate images"""
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
print("Paper detected - starting duplex scan\n")

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

# Wait for scan to complete
print("Waiting 8 seconds for both sides to scan...")
time.sleep(8)

# Check job info
print(f"\nJob URL: {job_url}")
job_info = requests.get(job_url, verify=False, timeout=10)
print(f"Job info status: {job_info.status_code}")
if "ImagesCompleted" in job_info.text:
    import re
    completed = re.search(r'<pwg:ImagesCompleted>(\d+)</pwg:ImagesCompleted>', job_info.text)
    if completed:
        print(f"Images completed: {completed.group(1)}")

# Fetch all available pages
images = []
for attempt in range(10):
    page_url = f"{job_url}/NextDocument"
    print(f"\nFetch attempt {attempt+1}...")

    response = requests.get(page_url, verify=False, timeout=120)
    print(f"  Status: {response.status_code}, Size: {len(response.content)}")

    if response.status_code == 200 and len(response.content) > 1000:
        img = Image.open(io.BytesIO(response.content))
        print(f"  Got image: {img.size[0]}x{img.size[1]} ({img.size[0]/300:.1f}x{img.size[1]/300:.1f} in)")
        images.append(img)
        time.sleep(1)
    elif response.status_code == 404:
        print("  No more pages")
        break
    else:
        print(f"  Waiting 2s and retrying...")
        time.sleep(2)

print(f"\n{'='*50}")
print(f"Total pages received: {len(images)}")
print("="*50)

for i, img in enumerate(images):
    path = f"C:/dev/scanner-web/test_scans/duplex4_p{i+1}.jpg"
    img.save(path, quality=90)
    print(f"Page {i+1}: {img.size[0]/300:.1f}x{img.size[1]/300:.1f} in -> {path}")
