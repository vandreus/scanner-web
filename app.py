"""
Scanner Web Controller
"""
import os, uuid, urllib3, requests, json, threading, io, time
from datetime import datetime
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import xml.etree.ElementTree as ET
from PIL import Image
import img2pdf

Image.MAX_IMAGE_PIXELS = 200000000
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
CORS(app)

CONFIG_FILE = os.environ.get('CONFIG_FILE', '/scans/.config/scanner.json')

DEFAULT_CONFIG = {
    "scanners": {
        "brother": {"name": "Brother", "ip": "10.69.7.167", "port": "443", "use_https": True, "type": "adf", "supports_duplex": True},
        "canon_feeder": {"name": "Canon Feeder", "ip": "10.69.7.107", "port": "80", "use_https": False, "type": "adf", "supports_duplex": True},
        "canon_flatbed": {"name": "Canon Flatbed", "ip": "10.69.7.107", "port": "80", "use_https": False, "type": "flatbed", "supports_duplex": False}
    },
    "selected_scanner": "brother",
    "destinations": {
        "receipt": {
            "folder": {"enabled": True, "path": "/scans/Receipts"},
            "molcom": {"enabled": True, "api_url": "https://molcom-expenses.vandreus.workers.dev/api/ingest/scanner-receipt", "secret": "", "default_tag": "scanned"}
        },
        "document": {
            "paperless": {"enabled": True, "path": "/paperless"},
            "folder": {"enabled": True, "path": "/scans/Documents"},
            "molcom": {"enabled": True, "api_url": "https://molcom-expenses.vandreus.workers.dev/api/ingest/scanner-receipt", "secret": "", "default_tag": "scanned"}
        }
    },
    "selected_destinations": {"receipt": "molcom", "document": "paperless"},
    "prefix": "Scan"
}

def load_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
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
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False

CONFIG = load_config()
SCANNER_STATUS = {}
STATUS_LOCK = threading.Lock()

def get_escl_base(scanner_id):
    scanner = CONFIG['scanners'].get(scanner_id)
    if not scanner:
        return None
    protocol = "https" if scanner.get('use_https', True) else "http"
    return f"{protocol}://{scanner.get('ip', '')}:{scanner.get('port', '443')}/eSCL"

def get_scanner_status(scanner_id):
    base_url = get_escl_base(scanner_id)
    if not base_url:
        return "Unknown"
    try:
        response = requests.get(f"{base_url}/ScannerStatus", verify=False, timeout=5)
        if response.status_code == 200:
            root = ET.fromstring(response.text)
            for elem in root.iter():
                if 'State' in elem.tag:
                    return elem.text
        return "Unknown"
    except:
        return "Offline"

def update_all_scanner_status():
    with STATUS_LOCK:
        for scanner_id in CONFIG['scanners']:
            SCANNER_STATUS[scanner_id] = get_scanner_status(scanner_id)

# Background keep-alive thread
KEEP_ALIVE_RUNNING = True

def scanner_keep_alive():
    """Background thread that pings scanners every 5 minutes to keep them awake"""
    while KEEP_ALIVE_RUNNING:
        try:
            for scanner_id in CONFIG['scanners']:
                base_url = get_escl_base(scanner_id)
                if base_url:
                    try:
                        requests.get(f"{base_url}/ScannerStatus", verify=False, timeout=5)
                    except:
                        pass
        except:
            pass
        time.sleep(300)

def start_keep_alive_thread():
    """Start the background keep-alive thread"""
    thread = threading.Thread(target=scanner_keep_alive, daemon=True)
    thread.start()
    print("Scanner keep-alive thread started (5 min interval)")

def create_scan_settings(scanner_id, duplex=False):
    scanner = CONFIG['scanners'].get(scanner_id, {})
    if scanner.get('type') == 'flatbed':
        input_source, max_height, duplex_element = "Platen", 4200, ""
    else:
        input_source = "Feeder"
        if duplex:
            max_height, duplex_element = 4200, "<scan:Duplex>true</scan:Duplex>"
        else:
            max_height, duplex_element = 36600, ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<scan:ScanSettings xmlns:scan="http://schemas.hp.com/imaging/escl/2011/05/03" xmlns:pwg="http://www.pwg.org/schemas/2010/12/sm">
    <pwg:Version>2.63</pwg:Version>
    <scan:Intent>Document</scan:Intent>
    <pwg:ScanRegions><pwg:ScanRegion><pwg:Height>{max_height}</pwg:Height><pwg:Width>2550</pwg:Width><pwg:XOffset>0</pwg:XOffset><pwg:YOffset>0</pwg:YOffset></pwg:ScanRegion></pwg:ScanRegions>
    <pwg:InputSource>{input_source}</pwg:InputSource>
    <scan:XResolution>300</scan:XResolution>
    <scan:YResolution>300</scan:YResolution>
    <scan:ColorMode>RGB24</scan:ColorMode>
    <pwg:DocumentFormat>image/jpeg</pwg:DocumentFormat>
    {duplex_element}
</scan:ScanSettings>"""

def scan_document(scanner_id, duplex=False):
    base_url = get_escl_base(scanner_id)
    if not base_url:
        return None
    scanner = CONFIG['scanners'].get(scanner_id, {})
    images = []
    try:
        response = requests.post(f"{base_url}/ScanJobs", data=create_scan_settings(scanner_id, duplex), headers={"Content-Type": "application/xml"}, verify=False, timeout=30)
        if response.status_code not in [201, 200]:
            return None
        job_url = response.headers.get('Location', '')
        if not job_url:
            job_url = f"{base_url}/ScanJobs/1"
        elif not job_url.startswith('http'):
            protocol = "https" if scanner.get('use_https', True) else "http"
            job_url = f"{protocol}://{scanner.get('ip')}:{scanner.get('port')}{job_url}"
        time.sleep(2)
        page_num = 1
        while page_num <= 100:
            try:
                page_response = requests.get(f"{job_url}/NextDocument", verify=False, timeout=120)
                if page_response.status_code == 200:
                    images.append(Image.open(io.BytesIO(page_response.content)))
                    page_num += 1
                    time.sleep(0.5)
                else:
                    break
            except:
                break
        return images if images else None
    except:
        return None

def auto_crop_image(img):
    try:
        if img.mode != 'RGB':
            img = img.convert('RGB')
        gray = img.convert('L')
        pixels = gray.load()
        width, height = gray.size
        paper_min_x, paper_min_y, paper_max_x, paper_max_y = width, height, 0, 0
        for y in range(0, height, 5):
            for x in range(0, width, 5):
                if pixels[x, y] > 220:
                    paper_min_x, paper_min_y = min(paper_min_x, x), min(paper_min_y, y)
                    paper_max_x, paper_max_y = max(paper_max_x, x), max(paper_max_y, y)
        if paper_max_x > paper_min_x and paper_max_y > paper_min_y:
            content_min_x, content_min_y, content_max_x, content_max_y = paper_max_x, paper_max_y, paper_min_x, paper_min_y
            for y in range(paper_min_y, paper_max_y, 3):
                for x in range(paper_min_x, paper_max_x, 3):
                    if pixels[x, y] < 150:
                        content_min_x, content_min_y = min(content_min_x, x), min(content_min_y, y)
                        content_max_x, content_max_y = max(content_max_x, x), max(content_max_y, y)
            if content_max_x > content_min_x and content_max_y > content_min_y:
                min_x, min_y, max_x, max_y = content_min_x, content_min_y, content_max_x, content_max_y
            else:
                min_x, min_y, max_x, max_y = paper_min_x, paper_min_y, paper_max_x, paper_max_y
            margin = 30
            return img.crop((max(0, min_x - margin), max(0, min_y - margin), min(width, max_x + margin), min(height, max_y + margin)))
        return img
    except:
        return img

def images_to_pdf_bytes(images):
    try:
        img_bytes_list = []
        for img in images:
            cropped = auto_crop_image(img)
            if cropped.mode != 'RGB':
                cropped = cropped.convert('RGB')
            buf = io.BytesIO()
            cropped.save(buf, format='JPEG', quality=90)
            img_bytes_list.append(buf.getvalue())
        return img2pdf.convert(img_bytes_list)
    except:
        return None

def save_pdf(pdf_bytes, output_path):
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'wb') as f:
            f.write(pdf_bytes)
        return True
    except:
        return False

def send_to_molcom(pdf_bytes, filename, profile, dest_config, tag=None, scanner_id=None):
    """POST scanned PDF to the Molcom Expenses ingest endpoint.
    Returns (ok, response_json) so callers can surface the new expense ID.
    Profile maps directly: 'receipt' → expense, 'document' → invoice/bill."""
    api_url = dest_config.get('api_url', '').strip()
    secret = dest_config.get('secret', '').strip()
    if not api_url or not secret:
        print("Molcom delivery failed: api_url/secret not configured")
        return False, None
    try:
        files = {'file': (filename, pdf_bytes, 'application/pdf')}
        data = {
            'profile': profile,
            'tag': (tag or dest_config.get('default_tag') or 'scanned'),
            'scanner': scanner_id or '',
        }
        headers = {'X-Scanner-Ingest-Secret': secret}
        resp = requests.post(api_url, files=files, data=data, headers=headers, timeout=120)
        if resp.status_code in (200, 201):
            print(f"Molcom: delivered {filename} → {resp.json()}")
            return True, resp.json()
        print(f"Molcom delivery failed [{resp.status_code}]: {resp.text[:200]}")
        return False, None
    except Exception as e:
        print(f"Molcom delivery error: {e}")
        return False, None

def deliver_pdf(pdf_bytes, filename, profile, destination, tag=None, scanner_id=None):
    """Dispatch a single PDF to the chosen destination. Returns either a bool
    (folder/paperless) or a tuple (ok, extra) when the destination yields
    structured response data (currently: 'molcom')."""
    dest_config = CONFIG['destinations'].get(profile, {}).get(destination, {})
    if destination == 'molcom':
        return send_to_molcom(pdf_bytes, filename, profile, dest_config, tag=tag, scanner_id=scanner_id)
    path = dest_config.get('path', '')
    return save_pdf(pdf_bytes, os.path.join(path, filename)) if path else False

MULTI_PAGE_SESSIONS = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def api_status():
    update_all_scanner_status()
    selected = CONFIG.get('selected_scanner', 'brother')
    scanners_info = {sid: {"name": s.get('name', sid), "status": SCANNER_STATUS.get(sid, 'Unknown'), "supports_duplex": s.get('supports_duplex', False), "type": s.get('type', 'adf')} for sid, s in CONFIG['scanners'].items()}
    return jsonify({"selected_scanner": selected, "scanners": scanners_info, "destinations": CONFIG.get('destinations', {}), "selected_destinations": CONFIG.get('selected_destinations', {})})

@app.route('/api/scanner/select', methods=['POST'])
def api_select_scanner():
    data = request.json or {}
    scanner_id = data.get('scanner')
    if scanner_id in CONFIG['scanners']:
        CONFIG['selected_scanner'] = scanner_id
        save_config(CONFIG)
        return jsonify({"success": True, "selected": scanner_id})
    return jsonify({"error": "Invalid scanner"}), 400

@app.route('/api/destination/select', methods=['POST'])
def api_select_destination():
    data = request.json or {}
    profile, destination = data.get('profile'), data.get('destination')
    if profile in ['receipt', 'document']:
        CONFIG.setdefault('selected_destinations', {})[profile] = destination
        save_config(CONFIG)
        return jsonify({"success": True})
    return jsonify({"error": "Invalid profile"}), 400

def _resolve_destination(data, profile):
    """Per-request override > config default. Used by all scan endpoints so the
    Molcom Expenses web app can force destination=molcom for in-app scans
    without mutating the user's standalone-UI preference."""
    override = (data or {}).get('destination')
    if override:
        return override
    return CONFIG.get('selected_destinations', {}).get(profile, 'folder')

def _resolve_scanner(data):
    return (data or {}).get('scanner') or CONFIG.get('selected_scanner', 'brother')

def _deliver_and_collect(pdf_bytes, filename, profile, destination, tag, scanner_id):
    """Wrap deliver_pdf so we get back (ok, extra) consistently. extra carries
    the Molcom response (expenseId, reviewUrl) when destination=molcom."""
    result = deliver_pdf(pdf_bytes, filename, profile, destination, tag=tag, scanner_id=scanner_id)
    if isinstance(result, tuple):
        return result
    return (bool(result), None)

@app.route('/api/scan', methods=['POST'])
def api_scan():
    data = request.json or {}
    preset, profile = data.get('preset', 'single'), data.get('profile', 'receipt')
    scanner_id = _resolve_scanner(data)
    destination = _resolve_destination(data, profile)
    tag = data.get('tag')
    duplex = preset == 'duplex_vertical'
    images = scan_document(scanner_id, duplex=duplex)
    if not images:
        return jsonify({"error": "Scan failed - no images received"}), 500
    prefix = CONFIG.get('prefix', 'Scan')
    timestamp_base = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    results = []
    sheets = [images[i:i+2] for i in range(0, len(images), 2)] if duplex else [[img] for img in images]
    for idx, sheet_images in enumerate(sheets):
        filename = f"{prefix}_{timestamp_base}_{idx+1:03d}.pdf" if len(sheets) > 1 else f"{prefix}_{timestamp_base}.pdf"
        pdf_bytes = images_to_pdf_bytes(sheet_images)
        if not pdf_bytes:
            continue
        ok, extra = _deliver_and_collect(pdf_bytes, filename, profile, destination, tag, scanner_id)
        if ok:
            entry = {"filename": filename, "pages": len(sheet_images)}
            if extra:
                entry["molcom"] = extra
            results.append(entry)
    if results:
        return jsonify({"success": True, "files": results, "total_sheets": len(results), "destination": destination, "profile": profile})
    return jsonify({"error": "No PDFs created"}), 500

@app.route('/api/scan/multi', methods=['POST'])
def api_scan_multi():
    """Multi-page scan - all pages in feeder go into 1 PDF"""
    data = request.json or {}
    profile = data.get('profile', 'receipt')
    duplex = data.get('duplex', False)
    scanner_id = _resolve_scanner(data)
    destination = _resolve_destination(data, profile)
    tag = data.get('tag')
    images = scan_document(scanner_id, duplex=duplex)
    if not images:
        return jsonify({"error": "Scan failed - no images received"}), 500
    prefix = CONFIG.get('prefix', 'Scan')
    filename = f"{prefix}_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.pdf"
    pdf_bytes = images_to_pdf_bytes(images)
    if not pdf_bytes:
        return jsonify({"error": "Failed to create PDF"}), 500
    ok, extra = _deliver_and_collect(pdf_bytes, filename, profile, destination, tag, scanner_id)
    if ok:
        payload = {"success": True, "filename": filename, "pages": len(images), "profile": profile, "destination": destination}
        if extra:
            payload["molcom"] = extra
        return jsonify(payload)
    return jsonify({"error": "Failed to deliver PDF"}), 500

@app.route('/api/scan/start', methods=['POST'])
def api_scan_start():
    session_id = str(uuid.uuid4())[:8]
    data = request.json or {}
    MULTI_PAGE_SESSIONS[session_id] = {
        "images": [],
        "profile": data.get('profile', 'receipt'),
        "scanner": _resolve_scanner(data),
        "duplex": data.get('duplex', False),
        # Carry the destination/tag overrides through to /done so the whole
        # session lands in the same place even if the user changes config mid-scan.
        "destination": data.get('destination'),
        "tag": data.get('tag'),
    }
    return jsonify({"success": True, "session_id": session_id})

@app.route('/api/scan/add/<session_id>', methods=['POST'])
def api_scan_add(session_id):
    if session_id not in MULTI_PAGE_SESSIONS:
        return jsonify({"error": "Invalid session"}), 400
    session = MULTI_PAGE_SESSIONS[session_id]
    images = scan_document(session.get('scanner', 'brother'), duplex=session.get('duplex', False))
    if not images:
        return jsonify({"error": "Scan failed - no images received"}), 500
    session["images"].extend(images)
    return jsonify({"success": True, "pages_added": len(images), "total_pages": len(session["images"])})

@app.route('/api/scan/done/<session_id>', methods=['POST'])
def api_scan_done(session_id):
    if session_id not in MULTI_PAGE_SESSIONS:
        return jsonify({"error": "Invalid session"}), 400
    session = MULTI_PAGE_SESSIONS[session_id]
    images = session["images"]
    if not images:
        del MULTI_PAGE_SESSIONS[session_id]
        return jsonify({"error": "No pages scanned"}), 400
    profile = session["profile"]
    destination = session.get("destination") or CONFIG.get('selected_destinations', {}).get(profile, 'folder')
    tag = session.get("tag")
    scanner_id = session.get("scanner")
    filename = f"{CONFIG.get('prefix', 'Scan')}_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.pdf"
    pdf_bytes = images_to_pdf_bytes(images)
    if not pdf_bytes:
        return jsonify({"error": "Failed to create PDF"}), 500
    ok, extra = _deliver_and_collect(pdf_bytes, filename, profile, destination, tag, scanner_id)
    if ok:
        del MULTI_PAGE_SESSIONS[session_id]
        payload = {"success": True, "filename": filename, "pages": len(images), "profile": profile, "destination": destination}
        if extra:
            payload["molcom"] = extra
        return jsonify(payload)
    return jsonify({"error": "Failed to deliver PDF"}), 500

@app.route('/api/scan/cancel/<session_id>', methods=['POST'])
def api_scan_cancel(session_id):
    MULTI_PAGE_SESSIONS.pop(session_id, None)
    return jsonify({"success": True})

@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    if request.method == 'POST':
        data = request.json or {}
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
    for profile, dests in CONFIG.get('destinations', {}).items():
        for dest, settings in dests.items():
            if settings.get('path'):
                os.makedirs(settings['path'], exist_ok=True)
    # Start the keep-alive thread
    start_keep_alive_thread()
    print("Scanner Web App Starting...")
    app.run(host='0.0.0.0', port=8080, debug=False)
