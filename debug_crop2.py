"""Debug: analyze the raw scan from test_scans folder"""
import os
from PIL import Image

# Check the raw scan we captured earlier
raw_path = "C:/dev/scanner-web/test_scans/raw_scan.jpg"

if not os.path.exists(raw_path):
    print(f"File not found: {raw_path}")
    exit()

img = Image.open(raw_path)
gray = img.convert('L')
pixels = gray.load()
width, height = gray.size

print(f"=== IMAGE ANALYSIS ===")
print(f"Size: {width}x{height} pixels")
print(f"Height in inches: {height/300:.1f}")

# Sample various areas
print(f"\n=== PIXEL VALUES ===")
print(f"Top-left (10,10): {pixels[10,10]}")
print(f"Top-right ({width-10},10): {pixels[width-10,10]}")
print(f"Bottom-left (10,{height-10}): {pixels[10,height-10]}")
print(f"Bottom-right ({width-10},{height-10}): {pixels[width-10,height-10]}")

# Sample down the middle
print(f"\nDown the center (x={width//2}):")
for y in range(0, height, height//10):
    print(f"  y={y} ({y/300:.1f} in): {pixels[width//2, y]}")

# Find where paper is (white pixels >220)
print(f"\n=== FINDING WHITE PAPER (pixels > 220) ===")
paper_min_y, paper_max_y = height, 0
paper_min_x, paper_max_x = width, 0

for y in range(0, height, 5):
    for x in range(0, width, 5):
        if pixels[x, y] > 220:
            paper_min_x = min(paper_min_x, x)
            paper_max_x = max(paper_max_x, x)
            paper_min_y = min(paper_min_y, y)
            paper_max_y = max(paper_max_y, y)

if paper_max_y > paper_min_y:
    print(f"Paper bounds: ({paper_min_x},{paper_min_y}) to ({paper_max_x},{paper_max_y})")
    print(f"Paper size: {(paper_max_x-paper_min_x)/300:.1f} x {(paper_max_y-paper_min_y)/300:.1f} inches")
else:
    print("No white paper detected (pixels > 220)")

# Find content (pixels < 150)
print(f"\n=== FINDING DARK CONTENT (pixels < 150) ===")
content_min_y, content_max_y = height, 0
content_min_x, content_max_x = width, 0

for y in range(0, height, 3):
    for x in range(0, width, 3):
        if pixels[x, y] < 150:
            content_min_x = min(content_min_x, x)
            content_max_x = max(content_max_x, x)
            content_min_y = min(content_min_y, y)
            content_max_y = max(content_max_y, y)

if content_max_y > content_min_y:
    print(f"Content bounds: ({content_min_x},{content_min_y}) to ({content_max_x},{content_max_y})")
    print(f"Content size: {(content_max_x-content_min_x)/300:.1f} x {(content_max_y-content_min_y)/300:.1f} inches")
else:
    print("No dark content detected (pixels < 150)")

# Distribution of pixel values
print(f"\n=== PIXEL DISTRIBUTION ===")
histogram = {}
for y in range(0, height, 10):
    for x in range(0, width, 10):
        bucket = pixels[x, y] // 25 * 25  # Group by 25
        histogram[bucket] = histogram.get(bucket, 0) + 1

for bucket in sorted(histogram.keys()):
    count = histogram[bucket]
    bar = '#' * min(50, count // 100)
    print(f"  {bucket:3d}-{bucket+24:3d}: {count:6d} {bar}")
