"""
Scanner Web Controller
Supports multiple scanners (Brother DS-940DW, Canon MF451DW) with eSCL protocol
Destinations: SparkReceipt (email), Paperless, Local folders
"""

import os
import ssl
import uuid
import urllib3
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from datetime import datetime
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import requests
import xml.etree.ElementTree as ET
from PIL import Image
import img2pdf
import io
import time
import json
import threading

# Increase PIL's max image size for large scans
Image.MAX_IMAGE_PIXELS = 200000000

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
CORS(app)

# Config file path
CONFIG_FILE = os.environ.get('CONFIG_FILE', '/scans/scanner_config.json')

# Default configuration
DEFAULT_CONFIG = {
    "scanners": {
        "brother": {
            "name": "Brother",
            "ip": "10.69.7.167",
            "port": "443",
            "use_https": True,
            "type": "adf",
            "supports_duplex": True
        },
        "canon_feeder": {
            "name": "Canon Feeder",
            "ip": "10.69.7.107",
            "port": "443",
            "use_https": True,
            "type": "adf",
            "supports_duplex": True
        },
        "canon_flatbed": {
            "name": "Canon Flatbed",
            "ip": "10.69.7.107",
            "port": "443",
            "use_https": True,
            "type": "flatbed",
            "supports_duplex": False
        }
    },
    "selected_scanner": "brother",
    "destinations": {
        "receipt": {
            "spark": {
                "enabled": True,
                "email": "entreprise-ahwp2+expense@to.sparkreceipt.com"
            },
            "folder": {
                "enabled": True,
                "path": "/scans/Receipts"
            }
        },
        "document": {
            "paperless": {
                "enabled": True,
                "path": "/paperless"
            },
            "folder": {
                "enabled": True,
                "path": "/scans/Documents"
            }
        }
    },
    "selected_destinations": {
        "receipt": "spark",
        "document": "paperless"
    },
    "smtp": {
        "host": "smtp",
        "port": 25,
        "use_tls": False,
        "username": "",
        "password": "",
        "from_email": "scanner@local"
    },
    "prefix": "Scan"
}

def load_config():
    """Load config from file or return defaults"""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                # Deep merge with defaults
                def merge(default, loaded):
                    for key in default:
                        if key not in loaded:
                            loaded[key] = default[key]
                        elif isinstance(default[key], dict) and isinstance(loaded[key], dict):
                            merge(default[key], loaded[key])
                    return loaded
                return merge(DEFAULT_CONFIG.copy(), config)
    except Exception as e:
        print(f"Error loading config: {e}")
    return DEFAULT_CONFIG.copy()

def save_config(config):
    """Save config to file"""
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False

# Load configuration
CONFIG = load_config()

# Scanner status cache
SCANNER_STATUS = {}
STATUS_LOCK = threading.Lock()

def get_escl_base(scanner_id):
    """Get the eSCL base URL for a scanner"""
    scanner = CONFIG['scanners'].get(scanner_id)
    if not scanner:
        return None
    protocol = "https" if scanner.get('use_https', True) else "http"
    ip = scanner.get('ip', '')
    port = scanner.get('port', '443')
    return f"{protocol}://{ip}:{port}/eSCL"

def get_scanner_status(scanner_id):
    """Check if scanner is ready"""
    base_url = get_escl_base(scanner_id)
    if not base_url:
        return "Unknown"

    try:
        response = requests.get(
            f"{base_url}/ScannerStatus",
            verify=False,
            timeout=5
        )
        if response.status_code == 200:
            root = ET.fromstring(response.text)
            ns = {'scan': 'http://schemas.hp.com/imaging/escl/2011/05/03'}
            state = root.find('.//scan:State', ns)
            if state is not None:
                return state.text
            for elem in root.iter():
                if 'State' in elem.tag:
                    return elem.text
        return "Unknown"
    except Exception as e:
        print(f"Error getting status for {scanner_id}: {e}")
        return "Offline"

def update_all_scanner_status():
    """Update status for all scanners"""
    with STATUS_LOCK:
        for scanner_id in CONFIG['scanners']:
            SCANNER_STATUS[scanner_id] = get_scanner_status(scanner_id)

def create_scan_settings(scanner_id, duplex=False):
    """Create eSCL scan settings XML"""
    scanner = CONFIG['scanners'].get(scanner_id, {})
    scanner_type = scanner.get('type', 'adf')

    # Set input source based on scanner type
    if scanner_type == 'flatbed':
        input_source = "Platen"
        max_height = 4200  # A4 height
        duplex_element = ""
    else:
        input_source = "Feeder"
        if duplex:
            max_height = 4200
            duplex_element = "<scan:Duplex>true</scan:Duplex>"
        else:
            max_height = 36600
            duplex_element = ""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<scan:ScanSettings xmlns:scan="http://schemas.hp.com/imaging/escl/2011/05/03"
                   xmlns:pwg="http://www.pwg.org/schemas/2010/12/sm">
    <pwg:Version>2.63</pwg:Version>
    <scan:Intent>Document</scan:Intent>
    <pwg:ScanRegions>
        <pwg:ScanRegion>
            <pwg:Height>{max_height}</pwg:Height>
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
    {duplex_element}
</scan:ScanSettings>"""

def scan_document(scanner_id, duplex=False):
    """
    Perform a scan and return all scanned pages as images
    Returns: List of PIL Image objects
    """
    base_url = get_escl_base(scanner_id)
    if not base_url:
        return None

    scanner = CONFIG['scanners'].get(scanner_id, {})
    images = []
    scan_settings = create_scan_settings(scanner_id, duplex=duplex)

    try:
        response = requests.post(
            f"{base_url}/ScanJobs",
            data=scan_settings,
            headers={"Content-Type": "application/xml"},
            verify=False,
            timeout=30
        )

        if response.status_code not in [201, 200]:
            print(f"Failed to create scan job: {response.status_code}")
            return None

        job_url = response.headers.get('Location', '')
        if not job_url:
            job_url = f"{base_url}/ScanJobs/1"
        elif not job_url.startswith('http'):
            protocol = "https" if scanner.get('use_https', True) else "http"
            ip = scanner.get('ip', '')
            port = scanner.get('port', '443')
            job_url = f"{protocol}://{ip}:{port}{job_url}"

        print(f"Scan job created: {job_url}")
        time.sleep(2)

        page_num = 1
        while page_num <= 100:
            try:
                page_response = requests.get(
                    f"{job_url}/NextDocument",
                    verify=False,
                    timeout=120
                )

                if page_response.status_code == 200:
                    img = Image.open(io.BytesIO(page_response.content))
                    images.append(img)
                    print(f"Got page {page_num}: {img.size}")
                    page_num += 1
                    time.sleep(0.5)
                elif page_response.status_code == 404:
                    print("No more pages")
                    break
                else:
                    print(f"Page fetch returned {page_response.status_code}")
                    break
            except Exception as e:
                print(f"Error fetching page: {e}")
                break

        return images if images else None
    except Exception as e:
        print(f"Scan error: {e}")
        return None

def auto_crop_image(img):
    """Auto-crop image to document area"""
    try:
        if img.mode != 'RGB':
            img = img.convert('RGB')

        gray = img.convert('L')
        pixels = gray.load()
        width, height = gray.size

        paper_min_x, paper_min_y = width, height
        paper_max_x, paper_max_y = 0, 0

        for y in range(0, height, 5):
            for x in range(0, width, 5):
                if pixels[x, y] > 220:
                    paper_min_x = min(paper_min_x, x)
                    paper_min_y = min(paper_min_y, y)
                    paper_max_x = max(paper_max_x, x)
                    paper_max_y = max(paper_max_y, y)

        if paper_max_x > paper_min_x and paper_max_y > paper_min_y:
            content_min_x, content_min_y = paper_max_x, paper_max_y
            content_max_x, content_max_y = paper_min_x, paper_min_y

            for y in range(paper_min_y, paper_max_y, 3):
                for x in range(paper_min_x, paper_max_x, 3):
                    if pixels[x, y] < 150:
                        content_min_x = min(content_min_x, x)
                        content_min_y = min(content_min_y, y)
                        content_max_x = max(content_max_x, x)
                        content_max_y = max(content_max_y, y)

            if content_max_x > content_min_x and content_max_y > content_min_y:
                min_x, min_y = content_min_x, content_min_y
                max_x, max_y = content_max_x, content_max_y
            else:
                min_x, min_y = paper_min_x, paper_min_y
                max_x, max_y = paper_max_x, paper_max_y

            margin = 30
            min_x = max(0, min_x - margin)
            min_y = max(0, min_y - margin)
            max_x = min(width, max_x + margin)
            max_y = min(height, max_y + margin)

            return img.crop((min_x, min_y, max_x, max_y))
        return img
    except Exception as e:
        print(f"Auto-crop error: {e}")
        return img

def images_to_pdf_bytes(images):
    """Convert list of PIL images to PDF bytes"""
    try:
        img_bytes_list = []
        for img in images:
            cropped = auto_crop_image(img)
            if cropped.mode != 'RGB':
                cropped = cropped.convert('RGB')
            img_buffer = io.BytesIO()
            cropped.save(img_buffer, format='JPEG', quality=90)
            img_bytes_list.append(img_buffer.getvalue())
        return img2pdf.convert(img_bytes_list)
    except Exception as e:
        print(f"PDF creation error: {e}")
        return None

def save_pdf(pdf_bytes, output_path):
    """Save PDF bytes to file"""
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'wb') as f:
            f.write(pdf_bytes)
        return True
    except Exception as e:
        print(f"Save error: {e}")
        return False

def send_email_with_pdf(pdf_bytes, filename, to_email):
    """Send PDF as email attachment via SMTP"""
    try:
        smtp_config = CONFIG.get('smtp', {})

        msg = MIMEMultipart()
        msg['From'] = smtp_config.get('from_email', 'scanner@local')
        msg['To'] = to_email
        msg['Subject'] = f"Scan: {filename}"

        msg.attach(MIMEText("Scanned document attached.", 'plain'))

        attachment = MIMEBase('application', 'pdf')
        attachment.set_payload(pdf_bytes)
        encoders.encode_base64(attachment)
        attachment.add_header('Content-Disposition', f'attachment; filename="{filename}"')
        msg.attach(attachment)

        with smtplib.SMTP(smtp_config.get('host', 'smtp'), smtp_config.get('port', 25)) as server:
            if smtp_config.get('use_tls'):
                server.starttls()
            if smtp_config.get('username'):
                server.login(smtp_config['username'], smtp_config['password'])
            server.send_message(msg)

        print(f"Email sent to {to_email}")
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

def get_destination_path(profile, destination):
    """Get the destination path/email for a profile"""
    dest_config = CONFIG['destinations'].get(profile, {}).get(destination, {})
    if destination == 'spark':
        return dest_config.get('email', '')
    return dest_config.get('path', '')

def deliver_pdf(pdf_bytes, filename, profile, destination):
    """Deliver PDF to the specified destination"""
    if destination == 'spark':
        email = get_destination_path(profile, destination)
        if email:
            return send_email_with_pdf(pdf_bytes, filename, email)
        return False
    else:
        path = get_destination_path(profile, destination)
        if path:
            output_path = os.path.join(path, filename)
            return save_pdf(pdf_bytes, output_path)
        return False

# Multi-page scan sessions
MULTI_PAGE_SESSIONS = {}

# Flask Routes

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def api_status():
    """Get status for all scanners"""
    update_all_scanner_status()
    selected = CONFIG.get('selected_scanner', 'brother')

    scanners_info = {}
    for scanner_id, scanner in CONFIG['scanners'].items():
        scanners_info[scanner_id] = {
            "name": scanner.get('name', scanner_id),
            "status": SCANNER_STATUS.get(scanner_id, 'Unknown'),
            "supports_duplex": scanner.get('supports_duplex', False),
            "type": scanner.get('type', 'adf')
        }

    return jsonify({
        "selected_scanner": selected,
        "scanners": scanners_info,
        "destinations": CONFIG.get('destinations', {}),
        "selected_destinations": CONFIG.get('selected_destinations', {})
    })

@app.route('/api/scanner/select', methods=['POST'])
def api_select_scanner():
    """Select active scanner"""
    data = request.json or {}
    scanner_id = data.get('scanner')
    if scanner_id in CONFIG['scanners']:
        CONFIG['selected_scanner'] = scanner_id
        save_config(CONFIG)
        return jsonify({"success": True, "selected": scanner_id})
    return jsonify({"error": "Invalid scanner"}), 400

@app.route('/api/destination/select', methods=['POST'])
def api_select_destination():
    """Select destination for a profile"""
    data = request.json or {}
    profile = data.get('profile')
    destination = data.get('destination')

    if profile in ['receipt', 'document']:
        if 'selected_destinations' not in CONFIG:
            CONFIG['selected_destinations'] = {}
        CONFIG['selected_destinations'][profile] = destination
        save_config(CONFIG)
        return jsonify({"success": True})
    return jsonify({"error": "Invalid profile"}), 400

@app.route('/api/scan', methods=['POST'])
def api_scan():
    """
    Perform a scan - creates separate PDFs for each physical sheet
    """
    data = request.json or {}
    preset = data.get('preset', 'single')
    profile = data.get('profile', 'receipt')

    scanner_id = CONFIG.get('selected_scanner', 'brother')
    destination = CONFIG.get('selected_destinations', {}).get(profile, 'folder')

    duplex = preset == 'duplex_vertical'

    # Scan all pages from feeder
    images = scan_document(scanner_id, duplex=duplex)

    if not images:
        return jsonify({"error": "Scan failed - no images received"}), 500

    prefix = CONFIG.get('prefix', 'Scan')
    timestamp_base = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    results = []

    if duplex:
        # Group images by physical sheets (2 pages per sheet)
        sheets = []
        for i in range(0, len(images), 2):
            sheet_images = images[i:i+2]
            sheets.append(sheet_images)
    else:
        # Each image is a separate sheet
        sheets = [[img] for img in images]

    # Create separate PDF for each sheet
    for idx, sheet_images in enumerate(sheets):
        if len(sheets) > 1:
            filename = f"{prefix}_{timestamp_base}_{idx+1:03d}.pdf"
        else:
            filename = f"{prefix}_{timestamp_base}.pdf"

        pdf_bytes = images_to_pdf_bytes(sheet_images)
        if pdf_bytes:
            if deliver_pdf(pdf_bytes, filename, profile, destination):
                results.append({"filename": filename, "pages": len(sheet_images)})
            else:
                results.append({"filename": filename, "error": "Delivery failed"})

    if results:
        return jsonify({
            "success": True,
            "files": results,
            "total_sheets": len(results),
            "destination": destination,
            "profile": profile
        })
    else:
        return jsonify({"error": "No PDFs created"}), 500

@app.route('/api/scan/start', methods=['POST'])
def api_scan_start():
    """Start a multi-page scan session"""
    session_id = str(uuid.uuid4())[:8]
    data = request.json or {}
    MULTI_PAGE_SESSIONS[session_id] = {
        "images": [],
        "profile": data.get('profile', 'receipt'),
        "scanner": CONFIG.get('selected_scanner', 'brother')
    }
    return jsonify({"success": True, "session_id": session_id})

@app.route('/api/scan/add/<session_id>', methods=['POST'])
def api_scan_add(session_id):
    """Scan and add pages to the session"""
    if session_id not in MULTI_PAGE_SESSIONS:
        return jsonify({"error": "Invalid session"}), 400

    session = MULTI_PAGE_SESSIONS[session_id]
    scanner_id = session.get('scanner', CONFIG.get('selected_scanner', 'brother'))

    images = scan_document(scanner_id, duplex=False)

    if not images:
        return jsonify({"error": "Scan failed - no images received"}), 500

    session["images"].extend(images)

    return jsonify({
        "success": True,
        "pages_added": len(images),
        "total_pages": len(session["images"])
    })

@app.route('/api/scan/done/<session_id>', methods=['POST'])
def api_scan_done(session_id):
    """Finish multi-page session and save single PDF"""
    if session_id not in MULTI_PAGE_SESSIONS:
        return jsonify({"error": "Invalid session"}), 400

    session = MULTI_PAGE_SESSIONS[session_id]
    images = session["images"]

    if not images:
        del MULTI_PAGE_SESSIONS[session_id]
        return jsonify({"error": "No pages scanned"}), 400

    profile = session["profile"]
    destination = CONFIG.get('selected_destinations', {}).get(profile, 'folder')
    prefix = CONFIG.get('prefix', 'Scan')

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    filename = f"{prefix}_{timestamp}.pdf"

    pdf_bytes = images_to_pdf_bytes(images)

    if pdf_bytes and deliver_pdf(pdf_bytes, filename, profile, destination):
        del MULTI_PAGE_SESSIONS[session_id]
        return jsonify({
            "success": True,
            "filename": filename,
            "pages": len(images),
            "profile": profile,
            "destination": destination
        })
    else:
        return jsonify({"error": "Failed to create/deliver PDF"}), 500

@app.route('/api/scan/cancel/<session_id>', methods=['POST'])
def api_scan_cancel(session_id):
    """Cancel multi-page session"""
    if session_id in MULTI_PAGE_SESSIONS:
        del MULTI_PAGE_SESSIONS[session_id]
    return jsonify({"success": True})

@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    """Get or update configuration"""
    if request.method == 'POST':
        data = request.json or {}
        # Update specific config values
        if 'smtp' in data:
            CONFIG['smtp'].update(data['smtp'])
        if 'destinations' in data:
            for profile, dests in data['destinations'].items():
                if profile in CONFIG['destinations']:
                    for dest, settings in dests.items():
                        if dest in CONFIG['destinations'][profile]:
                            CONFIG['destinations'][profile][dest].update(settings)
        if 'scanners' in data:
            for scanner_id, settings in data['scanners'].items():
                if scanner_id in CONFIG['scanners']:
                    CONFIG['scanners'][scanner_id].update(settings)
        save_config(CONFIG)
        return jsonify({"success": True})

    return jsonify(CONFIG)

if __name__ == '__main__':
    # Ensure destination folders exist
    for profile, dests in CONFIG.get('destinations', {}).items():
        for dest, settings in dests.items():
            path = settings.get('path', '')
            if path:
                os.makedirs(path, exist_ok=True)

    print("Scanner Web App Starting...")
    print(f"Config file: {CONFIG_FILE}")
    print("Scanners:")
    for scanner_id, scanner in CONFIG['scanners'].items():
        print(f"  {scanner_id}: {scanner.get('name')} ({scanner.get('ip')})")

    app.run(host='0.0.0.0', port=8080, debug=False)
