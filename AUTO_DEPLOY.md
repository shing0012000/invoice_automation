# Automated Render Deployment via API

This guide shows you how to deploy to Render **without using the web dashboard**.

## Quick Start

### Option 1: Use the Python Script (Easiest)

1. **Install required library**:
   ```bash
   pip install requests
   ```

2. **Get your Render API Key**:
   - Go to: https://dashboard.render.com/account/api-keys
   - Click "New API Key"
   - Copy the key

3. **Run the deployment script**:
   ```bash
   # Set API key as environment variable (recommended)
   export RENDER_API_KEY=your_api_key_here
   python3 deploy_to_render.py
   
   # Or enter it when prompted
   python3 deploy_to_render.py
   ```

4. **Follow the prompts**:
   - Choose what to create (database + service, service only, or database only)
   - Enter names if needed
   - Script will create everything automatically!

### Option 2: Use Render API Directly (Advanced)

If you prefer to use curl or another tool:

```bash
# Set your API key
export RENDER_API_KEY=your_api_key_here

# Get your owner ID
curl -H "Authorization: Bearer $RENDER_API_KEY" \
  https://api.render.com/v1/owners

# Create PostgreSQL database
curl -X POST \
  -H "Authorization: Bearer $RENDER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "invoice-automation-db",
    "databaseName": "invoices",
    "plan": "free",
    "region": "oregon"
  }' \
  https://api.render.com/v1/owners/{owner_id}/databases

# Create Web Service
curl -X POST \
  -H "Authorization: Bearer $RENDER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "web_service",
    "name": "invoice-automation",
    "repo": "shing0012000/invoice_automation",
    "branch": "main",
    "rootDir": "invoice_automation",
    "runtime": "docker",
    "plan": "free",
    "region": "oregon",
    "healthCheckPath": "/health"
  }' \
  https://api.render.com/v1/owners/{owner_id}/services
```

## What the Script Does

The `deploy_to_render.py` script automatically:

1. ✅ **Authenticates** with Render API using your API key
2. ✅ **Gets your owner ID** (user or team)
3. ✅ **Creates PostgreSQL database** (optional)
4. ✅ **Creates Web Service** with:
   - Docker runtime (for Tesseract OCR)
   - Environment variables from `render.yaml`
   - Health check path: `/health`
   - Links to your GitHub repository
5. ✅ **Links database to service** (if database created)
6. ✅ **Triggers deployment**

## After Deployment

1. **Check deployment status**:
   - Go to: https://dashboard.render.com
   - Your service will appear in the dashboard
   - Wait 2-5 minutes for build to complete

2. **Verify deployment**:
   ```bash
   curl https://your-service.onrender.com/health
   ```

3. **Add Gemini API key** (if using Level 3):
   - Go to Render Dashboard → Your Service → Environment
   - Add `GOOGLE_API_KEY` with your Gemini API key
   - Set `ENABLE_LEVEL_3_EXTRACTION=true`
   - Set `ENABLE_SEMANTIC_EXTRACTION=true`

## Troubleshooting

### API Key Issues
- Make sure your API key is valid
- Check it's not expired
- Verify you have permission to create services

### Repository Issues
- Ensure your GitHub repo is public or Render has access
- Check the repo name matches: `shing0012000/invoice_automation`
- Verify the branch is `main`

### Service Creation Fails
- Check Render API status: https://status.render.com
- Verify your account has available resources (free tier limits)
- Check API response for specific error messages

## API Documentation

Full Render API documentation: https://render.com/docs/api

## Security Note

⚠️ **Never commit your API key to git!**

Always use environment variables:
```bash
export RENDER_API_KEY=your_key_here
```

Or use a `.env` file (make sure it's in `.gitignore`).

