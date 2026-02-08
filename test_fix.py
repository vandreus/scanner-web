"""Test the fixed auto-crop on the long document"""
from PIL import Image
import img2pdf
import io
import os

# Increase decompression bomb limit
Image.MAX_IMAGE_PIXELS = 200000000

def auto_crop_image(img):
    """Fixed auto-crop that searches content WITHIN paper bounds"""
    gray = img.convert('L')
    pixels = gray.load()
    width, height = gray.size

    # Find paper (white >220)
    paper_min_x, paper_min_y = width, height
    paper_max_x, paper_max_y = 0, 0

    for y in range(0, height, 5):
        for x in range(0, width, 5):
            if pixels[x, y] > 220:
                paper_min_x = min(paper_min_x, x)
                paper_min_y = min(paper_min_y, y)
                paper_max_x = max(paper_max_x, x)
                paper_max_y = max(paper_max_y, y)

    print(f"Paper: ({paper_min_x},{paper_min_y}) to ({paper_max_x},{paper_max_y})")
    print(f"Paper size: {(paper_max_x-paper_min_x)/300:.1f} x {(paper_max_y-paper_min_y)/300:.1f} inches")

    if paper_max_x > paper_min_x and paper_max_y > paper_min_y:
        # Find content WITHIN paper bounds only
        content_min_x, content_min_y = paper_max_x, paper_max_y
        content_max_x, content_max_y = paper_min_x, paper_min_y

        for y in range(paper_min_y, paper_max_y, 3):
            for x in range(paper_min_x, paper_max_x, 3):
                if pixels[x, y] < 150:
                    content_min_x = min(content_min_x, x)
                    content_min_y = min(content_min_y, y)
                    content_max_x = max(content_max_x, x)
                    content_max_y = max(content_max_y, y)

        if content_max_x > content_min_x:
            print(f"Content within paper: ({content_min_x},{content_min_y}) to ({content_max_x},{content_max_y})")
            print(f"Content size: {(content_max_x-content_min_x)/300:.1f} x {(content_max_y-content_min_y)/300:.1f} inches")
            min_x, min_y = content_min_x, content_min_y
            max_x, max_y = content_max_x, content_max_y
        else:
            print("No content found, using paper bounds")
            min_x, min_y = paper_min_x, paper_min_y
            max_x, max_y = paper_max_x, paper_max_y

        # Margin
        margin = 30
        min_x = max(0, min_x - margin)
        min_y = max(0, min_y - margin)
        max_x = min(width, max_x + margin)
        max_y = min(height, max_y + margin)

        return img.crop((min_x, min_y, max_x, max_y))

    return img

# Load the raw long doc scan
raw_path = "C:/dev/scanner-web/test_scans/long_doc_raw.jpg"
img = Image.open(raw_path)
print(f"Original: {img.size[0]}x{img.size[1]} = {img.size[0]/300:.1f} x {img.size[1]/300:.1f} inches")

# Crop
print("\nCropping...")
cropped = auto_crop_image(img)
print(f"\nCropped: {cropped.size[0]}x{cropped.size[1]} = {cropped.size[0]/300:.1f} x {cropped.size[1]/300:.1f} inches")

# Save
cropped_path = "C:/dev/scanner-web/test_scans/long_doc_fixed.jpg"
cropped.save(cropped_path, quality=90)
print(f"Saved: {cropped_path}")

# PDF
pdf_path = "C:/dev/scanner-web/test_scans/long_doc_fixed.pdf"
if cropped.mode != 'RGB':
    cropped = cropped.convert('RGB')
buf = io.BytesIO()
cropped.save(buf, format='JPEG', quality=90)
pdf_bytes = img2pdf.convert([buf.getvalue()])
with open(pdf_path, 'wb') as f:
    f.write(pdf_bytes)
print(f"PDF: {pdf_path} ({os.path.getsize(pdf_path)/1024:.1f} KB)")
