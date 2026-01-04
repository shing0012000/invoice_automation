#!/bin/bash
# Build script for Render deployment
# Installs Tesseract OCR and Python dependencies

set -e  # Exit on error

echo "=========================================="
echo "Installing Tesseract OCR for Render"
echo "=========================================="

# Update package list
apt-get update

# Install Tesseract OCR and English language data
apt-get install -y tesseract-ocr tesseract-ocr-eng

# Verify Tesseract installation
echo "Verifying Tesseract installation..."
tesseract --version || echo "WARNING: Tesseract version check failed"

echo "=========================================="
echo "Installing Python dependencies"
echo "=========================================="

# Install Python dependencies
pip install --no-cache-dir -r requirements.txt

echo "=========================================="
echo "Build complete!"
echo "=========================================="

