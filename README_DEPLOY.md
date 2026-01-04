# 🚀 One-Command Deployment to Render

## The Easiest Way (Just 2 Steps!)

### Step 1: Get Your Render API Key
1. Go to: **https://dashboard.render.com/account/api-keys**
2. Click **"New API Key"**
3. Copy the key

### Step 2: Run This Command
```bash
export RENDER_API_KEY=your_key_here && ./QUICK_DEPLOY.sh
```

**That's it!** The script will:
- ✅ Install dependencies automatically
- ✅ Create PostgreSQL database
- ✅ Create Web Service
- ✅ Configure all settings
- ✅ Deploy your app

## What Gets Created Automatically

1. **PostgreSQL Database**
   - Name: `invoice-automation-db`
   - Automatically linked to your service

2. **Web Service**
   - Uses Docker (for Tesseract OCR)
   - Configured from `render.yaml`
   - Health check: `/health`
   - Auto-deploys from GitHub

3. **Environment Variables**
   - `DEMO_MODE=true`
   - `DATABASE_URL` (auto-linked)
   - All settings from `render.yaml`

## Alternative: Manual Script

If you prefer more control:

```bash
# Install requests
pip install requests

# Run deployment script
export RENDER_API_KEY=your_key_here
python3 deploy_to_render.py
```

The script will ask you:
- Create database + service? (recommended)
- Create service only? (if you have existing database)
- Create database only? (if you just need database)

## After Deployment

1. **Check Status**: https://dashboard.render.com
2. **Wait 2-5 minutes** for build to complete
3. **Test**: `curl https://your-service.onrender.com/health`
4. **Add Gemini** (optional): Set `GOOGLE_API_KEY` in Render Dashboard

## Troubleshooting

### "requests not found"
```bash
pip install requests
```

### "API key invalid"
- Make sure you copied the full key
- Check it's not expired
- Get a new key from Render dashboard

### "Repository not found"
- Ensure GitHub repo is public or Render has access
- Check repo name: `shing0012000/invoice_automation`

## Full Documentation

- **API Deployment**: See [AUTO_DEPLOY.md](AUTO_DEPLOY.md)
- **Manual Deployment**: See [DEPLOY.md](DEPLOY.md)
- **General Guide**: See [README.md](README.md)

