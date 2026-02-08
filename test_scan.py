"""
Test actual scanning with Brother DS-940DW via eSCL
"""

import requests
import urllib3
import time
import os
from datetime import datetime
from PIL import Image
import img2pdf
import io

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SCANNER_IP = "10.69.7.167"
ESCL_BASE = f"https://{SCANNER_IP}:443/eSCL"
SAVE_FOLDER = "C:/dev/scanner-web/test_scans"

def get_scanner_status():
    """Check scanner status"""
    try:
        response = requests.get(f"{ESCL_BASE}/ScannerStatus", verify=False, timeout=5)
        if response.status_code == 200:
            if "Idle" in response.text:
                return "Idle"
            elif "Processing" in response.text:
                return "Processing"
            elif "ScannerAdfEmpty" in response.text:
                return "ADF Empty"
        return "Unknown"
    except Exception as e:
        return f"Error: {e}"

def create_scan_settings(duplex=False):
    """Create eSCL scan request XML"""

    if duplex:
        input_source = "Feeder"
        duplex_setting = "<scan:Duplex>true</scan:Duplex>"
    else:
        input_source = "Feeder"
        duplex_setting = "<scan:Duplex>false</scan:Duplex>"

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<scan:ScanSettings xmlns:scan="http://schemas.hp.com/imaging/escl/2011/05/03"
                   xmlns:pwg="http://www.pwg.org/schemas/2010/12/sm">
    <pwg:Version>2.63</pwg:Version>
    <scan:Intent>Document</scan:Intent>
    <pwg:ScanRegions>
        <pwg:ScanRegion>
            <pwg:Height>3300</pwg:Height>
            <pwg:Width>2550</pwg:Width>
            <pwg:XOffset>0</pwg:XOffset>
            <pwg:YOffset>0</pwg:YOffset>
        </pwg:ScanRegion>
    </pwg:ScanRegions>
    <pwg:InputSource>{input_source}</pwg:InputSource>
    <scan:XResolution>300</scan:XResolution>
    <scan:YResolution>300</scan:YResolution>
    <scan:ColorMode>RGB24</scan:ColorMode>
    <pwg:DocumentFormat>image/jpeg</pwg:DocumentFormat>
    {duplex_setting}
</scan:ScanSettings>"""

def auto_crop_image(img):
    """Auto-crop to content - detect document edges against scanner background"""
    try:
        if img.mode != 'RGB':
            img = img.convert('RGB')

        gray = img.convert('L')
        pixels = gray.load()
        width, height = gray.size

        # For receipt/document scanning, detect the paper edge
        # Scanner background is usually very dark (near black) or very light
        # Paper is typically lighter than dark scanner bed

        min_x, min_y = width, height
        max_x, max_y = 0, 0

        # Use edge detection - look for significant brightness changes
        # Threshold for "content" vs "background"
        threshold = 230  # Lighter threshold - paper is usually < 230

        # Sample every 3rd pixel for better accuracy
        for y in range(0, height, 3):
            for x in range(0, width, 3):
                pixel_val = pixels[x, y]
                # Content is anything that's not pure white/near-white
                if pixel_val < threshold:
                    min_x = min(min_x, x)
                    min_y = min(min_y, y)
                    max_x = max(max_x, x)
                    max_y = max(max_y, y)

        # Check if we found meaningful bounds (at least 10% of original)
        if (max_x - min_x) > width * 0.1 and (max_y - min_y) > height * 0.1:
            margin = 15
            min_x = max(0, min_x - margin)
            min_y = max(0, min_y - margin)
            max_x = min(width, max_x + margin)
            max_y = min(height, max_y + margin)

            cropped = img.crop((min_x, min_y, max_x, max_y))
            return cropped

        return img
    except Exception as e:
        print(f"    Auto-crop error: {e}")
        return img

def scan_document(duplex=False):
    """Perform scan and return images"""
    print(f"\n[SCAN] Starting {'duplex' if duplex else 'simplex'} scan...")

    # Check status first
    status = get_scanner_status()
    print(f"[SCAN] Scanner status: {status}")

    if "Empty" in status:
        print("[SCAN] ERROR: No paper in ADF!")
        return None

    # Create scan job
    scan_settings = create_scan_settings(duplex=duplex)
    print(f"[SCAN] Creating scan job...")

    try:
        response = requests.post(
            f"{ESCL_BASE}/ScanJobs",
            data=scan_settings,
            headers={"Content-Type": "application/xml"},
            verify=False,
            timeout=30
        )

        print(f"[SCAN] Create job response: {response.status_code}")

        if response.status_code not in [201, 200]:
            print(f"[SCAN] Failed to create job: {response.text[:500]}")
            return None

        # Get job URL from Location header
        job_url = response.headers.get('Location', '')
        print(f"[SCAN] Job location: {job_url}")

        if not job_url:
            # Try default
            job_url = f"{ESCL_BASE}/ScanJobs/1"
        elif not job_url.startswith('http'):
            job_url = f"https://{SCANNER_IP}:443{job_url}"

        # Wait for scanner to process
        print("[SCAN] Waiting for scanner...")
        time.sleep(2)

        # Fetch pages
        images = []
        page_num = 1
        max_pages = 50

        while page_num <= max_pages:
            page_url = f"{job_url}/NextDocument"
            print(f"[SCAN] Fetching page {page_num}...")

            try:
                page_response = requests.get(
                    page_url,
                    verify=False,
                    timeout=120
                )

                print(f"[SCAN] Page {page_num} response: {page_response.status_code}")

                if page_response.status_code == 200:
                    content_type = page_response.headers.get('Content-Type', '')
                    print(f"[SCAN] Content-Type: {content_type}, Size: {len(page_response.content)} bytes")

                    img = Image.open(io.BytesIO(page_response.content))
                    print(f"[SCAN] Got page {page_num}: {img.size[0]}x{img.size[1]}")
                    images.append(img)
                    page_num += 1
                    time.sleep(0.5)

                elif page_response.status_code == 404:
                    print("[SCAN] No more pages (404)")
                    break
                else:
                    print(f"[SCAN] Unexpected response: {page_response.status_code}")
                    print(f"[SCAN] Body: {page_response.text[:300]}")
                    break

            except Exception as e:
                print(f"[SCAN] Error fetching page: {e}")
                break

        return images if images else None

    except Exception as e:
        print(f"[SCAN] Error: {e}")
        return None

def save_as_pdf(images, filename):
    """Save images as PDF with auto-crop"""
    print(f"\n[PDF] Processing {len(images)} page(s)...")

    os.makedirs(SAVE_FOLDER, exist_ok=True)
    output_path = os.path.join(SAVE_FOLDER, filename)

    img_bytes_list = []
    for i, img in enumerate(images):
        print(f"[PDF] Auto-cropping page {i+1}...")
        cropped = auto_crop_image(img)
        print(f"[PDF] Page {i+1}: {img.size[0]}x{img.size[1]} -> {cropped.size[0]}x{cropped.size[1]}")

        if cropped.mode != 'RGB':
            cropped = cropped.convert('RGB')

        img_buffer = io.BytesIO()
        cropped.save(img_buffer, format='JPEG', quality=90)
        img_bytes_list.append(img_buffer.getvalue())

    print(f"[PDF] Creating PDF...")
    pdf_bytes = img2pdf.convert(img_bytes_list)

    with open(output_path, 'wb') as f:
        f.write(pdf_bytes)

    print(f"[PDF] Saved: {output_path}")
    print(f"[PDF] Size: {os.path.getsize(output_path) / 1024:.1f} KB")
    return output_path

if __name__ == "__main__":
    print("="*50)
    print("Brother DS-940DW Scan Test")
    print("="*50)
    print(f"Scanner: {SCANNER_IP}")
    print(f"Save to: {SAVE_FOLDER}")

    # Check status
    status = get_scanner_status()
    print(f"\nScanner Status: {status}")

    if "Empty" in status:
        print("\n*** Please load paper into the ADF and run again ***")
    else:
        # Perform single-sided scan
        print("\n--- Testing SINGLE-SIDED scan ---")
        images = scan_document(duplex=False)

        if images:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            filename = f"Scan_{timestamp}.pdf"
            pdf_path = save_as_pdf(images, filename)
            print(f"\n*** SUCCESS! Scanned {len(images)} page(s) ***")
            print(f"*** PDF saved to: {pdf_path} ***")
        else:
            print("\n*** SCAN FAILED - No images received ***")

    print("\n" + "="*50)
