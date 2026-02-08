FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app.py .
COPY templates/ templates/

# Create default scan folders
RUN mkdir -p /scans/Receipts /scans/Documents

# Environment variables (defaults - can be changed via web UI)
ENV SCANNER_IP=10.69.7.167
ENV SCANNER_PORT=443
ENV USE_HTTPS=true
ENV RECEIPT_FOLDER=/scans/Receipts
ENV DOCUMENT_FOLDER=/scans/Documents
ENV CONFIG_FILE=/scans/scanner_config.json

EXPOSE 8080

CMD ["python", "app.py"]
