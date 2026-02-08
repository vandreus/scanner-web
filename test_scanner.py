"""
Test script to verify eSCL connectivity with Brother DS-940DW
"""

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SCANNER_IP = "10.69.7.167"

def test_connection(protocol, port):
    base_url = f"{protocol}://{SCANNER_IP}:{port}/eSCL"

    print(f"\n{'='*50}")
    print(f"Testing: {base_url}")
    print('='*50)

    try:
        print(f"\n[1] GET /ScannerCapabilities ...")
        response = requests.get(
            f"{base_url}/ScannerCapabilities",
            verify=False,
            timeout=10
        )
        print(f"    Status: {response.status_code}")
        if response.status_code == 200:
            print(f"    SUCCESS! Scanner supports eSCL")
            print(f"    Response length: {len(response.text)} bytes")
            print(f"\n    Preview:\n{response.text[:1500]}")
            return True, response.text
        else:
            print(f"    Failed: {response.status_code}")
    except Exception as e:
        print(f"    Error: {e}")

    return False, None

def test_status(protocol, port):
    base_url = f"{protocol}://{SCANNER_IP}:{port}/eSCL"
    try:
        print(f"\n[2] GET /ScannerStatus ...")
        response = requests.get(
            f"{base_url}/ScannerStatus",
            verify=False,
            timeout=10
        )
        print(f"    Status: {response.status_code}")
        if response.status_code == 200:
            print(f"    Response:\n{response.text}")
    except Exception as e:
        print(f"    Error: {e}")

if __name__ == "__main__":
    print("Brother DS-940DW eSCL Connection Test")
    print(f"Scanner IP: {SCANNER_IP}")

    success, caps = test_connection("https", 443)

    if success:
        test_status("https", 443)
        print("\n" + "="*50)
        print("SUCCESS - Scanner eSCL connectivity confirmed!")
        print("Protocol: HTTPS, Port: 443")
        print("="*50)
    else:
        print("\nFailed to connect via eSCL")
