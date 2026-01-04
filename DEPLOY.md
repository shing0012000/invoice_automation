# Automated Render Deployment Guide

This guide helps you deploy to Render with minimal manual configuration.

## Quick Deploy (Using render.yaml)

If you have `render.yaml` in your repository, Render can automatically configure your service:

1. **Push your code to GitHub** (if not already done)
   ```bash
   git add .
   git commit -m "Add Dockerfile and render.yaml for automated deployment"
   git push origin main
   ```

2. **Create a new Web Service in Render**
   - Go to [Render Dashboard](https://dashboard.render.com)
   - Click "New +" → "Web Service"
   - Connect your GitHub repository
   - Select the repository: `shing0012000/invoice_automation`
   - Render will automatically detect `render.yaml` and use it

3. **Create a PostgreSQL Database** (if you don't have one)
   - In Render Dashboard, click "New +" → "PostgreSQL"
   - Name it (e.g., `invoice-automation-db`)
   - Render will automatically provide `DATABASE_URL` environment variable
   - Link it to your web service

4. **Set Environment Variables** (if needed)
   - Go to your Web Service → Environment
   - If using Gemini (Level 3), set:
     - `GOOGLE_API_KEY`: Your Gemini API key
     - `ENABLE_LEVEL_3_EXTRACTION`: `true`
     - `ENABLE_SEMANTIC_EXTRACTION`: `true`

5. **Deploy**
   - Render will automatically build using Dockerfile
   - Tesseract OCR will be installed automatically
   - Service will be available at `https://your-app.onrender.com`

## Manual Configuration (If render.yaml doesn't work)

If Render doesn't automatically use `render.yaml`, configure manually:

### 1. Environment Settings
- **Environment**: Docker
- **Dockerfile Path**: `./Dockerfile`
- **Docker Context**: `.`

### 2. Build & Deploy Settings
- **Build Command**: (leave empty - Docker handles it)
- **Start Command**: (leave empty - defined in Dockerfile)
- **Health Check Path**: `/health`

### 3. Environment Variables
Set these in Render Dashboard → Environment:

```
DATABASE_URL=postgresql+psycopg://... (from your PostgreSQL database)
DEMO_MODE=true
ENABLE_LEVEL_3_EXTRACTION=false (or true if using Gemini)
ENABLE_SEMANTIC_EXTRACTION=false (or true if using Gemini)
GOOGLE_API_KEY=your_key_here (only if using Level 3)
USE_LLM_FALLBACK=true
MIN_EXTRACTION_RATE=0.5
STORAGE_DIR=./storage
```

## What Gets Installed Automatically

The Dockerfile automatically installs:
- ✅ Python 3.13
- ✅ Tesseract OCR (`tesseract-ocr` and `tesseract-ocr-eng`)
- ✅ All Python dependencies from `requirements.txt`
- ✅ Application code

## Verification

After deployment, check:

1. **Health Check**: `curl https://your-app.onrender.com/health`
   - Should return: `{"status":"healthy","service":"invoice-automation","database":"connected","demo_mode":true}`

2. **Logs**: Check Render logs for:
   - "Installing Tesseract OCR" (in Docker build)
   - "Database dialect: postgresql"
   - "Tesseract OCR" verification

3. **Test Upload**: Upload an image to verify Tesseract is working

## Troubleshooting

### If Docker build fails:
- Check Render logs for specific error
- Verify Dockerfile syntax
- Ensure all files are committed to GitHub

### If Tesseract not found:
- Check Docker build logs for Tesseract installation
- Verify Dockerfile includes `tesseract-ocr` packages
- Check application logs for Tesseract path detection

### If database connection fails:
- Verify `DATABASE_URL` is set correctly
- Check PostgreSQL database is running
- Ensure database is linked to web service

## Next Steps

Once deployed:
1. Test the health endpoint
2. Upload a test invoice (PDF or image)
3. Verify extraction works
4. Check logs for any issues

