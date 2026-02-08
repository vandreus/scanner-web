"""Check scanner status and try to clear any stuck jobs"""
import requests
import urllib3
urllib3.disable_warnings()

SCANNER_IP = "10.69.7.167"
ESCL_BASE = f"https://{SCANNER_IP}:443/eSCL"

# Check status
print("Checking scanner status...")
try:
    response = requests.get(f"{ESCL_BASE}/ScannerStatus", verify=False, timeout=5)
    print(f"Status code: {response.status_code}")
    print(f"Response:\n{response.text}")
except Exception as e:
    print(f"Error: {e}")

# Try to delete any existing jobs
print("\nTrying to clear jobs 1-5...")
for job_id in range(1, 6):
    try:
        job_url = f"{ESCL_BASE}/ScanJobs/{job_id}"
        response = requests.delete(job_url, verify=False, timeout=5)
        print(f"  Delete job {job_id}: {response.status_code}")
    except Exception as e:
        print(f"  Delete job {job_id}: Error - {e}")

# Check status again
print("\nFinal status check...")
try:
    response = requests.get(f"{ESCL_BASE}/ScannerStatus", verify=False, timeout=5)
    print(f"Status: {response.status_code}")
    if "Idle" in response.text:
        print("Scanner is IDLE - ready to scan")
    elif "Processing" in response.text:
        print("Scanner is PROCESSING")
    else:
        print(f"Response: {response.text[:500]}")
except Exception as e:
    print(f"Error: {e}")
