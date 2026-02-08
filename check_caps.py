"""Check scanner capabilities for duplex format"""
import requests
import urllib3
urllib3.disable_warnings()

SCANNER_IP = "10.69.7.167"
ESCL_BASE = f"https://{SCANNER_IP}:443/eSCL"

# Get full capabilities
response = requests.get(f"{ESCL_BASE}/ScannerCapabilities", verify=False, timeout=10)
caps = response.text

# Save to file for analysis
with open("C:/dev/scanner-web/scanner_caps.xml", "w") as f:
    f.write(caps)
print("Saved capabilities to scanner_caps.xml")

# Search for duplex-related settings
print("\nSearching for duplex-related XML elements...")
import re

# Find all elements containing 'duplex' (case insensitive)
lines = caps.split('\n')
for i, line in enumerate(lines):
    if 'uplex' in line.lower():
        print(f"Line {i}: {line.strip()}")

# Find AdfDuplexInputCaps section
if "AdfDuplexInputCaps" in caps:
    print("\n=== AdfDuplexInputCaps section found! ===")
    start = caps.find("<scan:AdfDuplexInputCaps>")
    end = caps.find("</scan:AdfDuplexInputCaps>") + 26
    print(caps[start:end])
