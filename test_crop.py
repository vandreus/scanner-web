"""Test the improved auto-crop on the raw scan"""
from PIL import Image
import img2pdf
import io

def auto_crop_image(img):
    """
    Auto-crop image to document area.
    DS-940DW scanner background is gray (~180-195).
    Paper is white (255), content/text is darker (<150).
    """
    if img.mode != 'RGB':
        img = img.convert('RGB')

    gray = img.convert('L')
    pixels = gray.load()
    width, height = gray.size

    min_x, min_y = width, height
    max_x, max_y = 0, 0
    content_threshold = 150

    for y in range(0, height, 3):
        for x in range(0, width, 3):
            if pixels[x, y] < content_threshold:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)

    if max_x > min_x and max_y > min_y:
        margin = 30
        min_x = max(0, min_x - margin)
        min_y = max(0, min_y - margin)
        max_x = min(width, max_x + margin)
        max_y = min(height, max_y + margin)

        return img.crop((min_x, min_y, max_x, max_y))

    return img

# Load raw scan
img = Image.open("C:/dev/scanner-web/test_scans/raw_scan.jpg")
print(f"Original size: {img.size[0]}x{img.size[1]}")

# Crop it
cropped = auto_crop_image(img)
print(f"Cropped size: {cropped.size[0]}x{cropped.size[1]}")

# Save cropped JPEG
cropped.save("C:/dev/scanner-web/test_scans/cropped_scan.jpg", quality=90)
print("Saved: cropped_scan.jpg")

# Save as PDF
if cropped.mode != 'RGB':
    cropped = cropped.convert('RGB')
img_buffer = io.BytesIO()
cropped.save(img_buffer, format='JPEG', quality=90)
pdf_bytes = img2pdf.convert([img_buffer.getvalue()])

with open("C:/dev/scanner-web/test_scans/cropped_scan.pdf", 'wb') as f:
    f.write(pdf_bytes)
print("Saved: cropped_scan.pdf")

import os
orig_size = os.path.getsize("C:/dev/scanner-web/test_scans/raw_scan.jpg")
crop_size = os.path.getsize("C:/dev/scanner-web/test_scans/cropped_scan.jpg")
pdf_size = os.path.getsize("C:/dev/scanner-web/test_scans/cropped_scan.pdf")
print(f"\nFile sizes:")
print(f"  Original JPEG: {orig_size/1024:.1f} KB")
print(f"  Cropped JPEG: {crop_size/1024:.1f} KB")
print(f"  Cropped PDF: {pdf_size/1024:.1f} KB")
