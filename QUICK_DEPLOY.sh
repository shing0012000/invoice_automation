#!/bin/bash
# Quick deployment script - does everything possible automatically

echo "=========================================="
echo "Quick Render Deployment Setup"
echo "=========================================="

# Check if requests is installed
echo ""
echo "Checking dependencies..."
if python3 -c "import requests" 2>/dev/null; then
    echo "✅ requests library installed"
else
    echo "📦 Installing requests library..."
    pip install requests -q
    if [ $? -eq 0 ]; then
        echo "✅ requests installed"
    else
        echo "❌ Failed to install requests"
        echo "   Please run manually: pip install requests"
        exit 1
    fi
fi

# Check if API key is set
if [ -z "$RENDER_API_KEY" ]; then
    echo ""
    echo "=========================================="
    echo "Render API Key Required"
    echo "=========================================="
    echo "To get your API key:"
    echo "1. Go to: https://dashboard.render.com/account/api-keys"
    echo "2. Click 'New API Key'"
    echo "3. Copy the key"
    echo ""
    echo "Then run:"
    echo "  export RENDER_API_KEY=your_key_here"
    echo "  ./QUICK_DEPLOY.sh"
    echo ""
    echo "Or enter it now (will not be saved):"
    read -sp "Enter Render API Key: " RENDER_API_KEY
    echo ""
    export RENDER_API_KEY
fi

if [ -z "$RENDER_API_KEY" ]; then
    echo "❌ API key is required. Exiting."
    exit 1
fi

echo ""
echo "=========================================="
echo "Starting Automated Deployment"
echo "=========================================="
echo ""

# Run the deployment script
python3 deploy_to_render.py

echo ""
echo "=========================================="
echo "Deployment Script Complete"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Check Render Dashboard: https://dashboard.render.com"
echo "2. Wait 2-5 minutes for deployment"
echo "3. Test: curl https://your-service.onrender.com/health"

