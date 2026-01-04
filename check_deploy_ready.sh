#!/bin/bash
# Check if project is ready for Render deployment

echo "=========================================="
echo "Render Deployment Readiness Check"
echo "=========================================="

ERRORS=0
WARNINGS=0

# Check for required files
echo ""
echo "Checking required files..."

if [ -f "Dockerfile" ]; then
    echo "✅ Dockerfile exists"
else
    echo "❌ Dockerfile missing"
    ERRORS=$((ERRORS + 1))
fi

if [ -f "render.yaml" ]; then
    echo "✅ render.yaml exists"
else
    echo "⚠️  render.yaml missing (optional, but recommended)"
    WARNINGS=$((WARNINGS + 1))
fi

if [ -f "Procfile" ]; then
    echo "✅ Procfile exists"
else
    echo "⚠️  Procfile missing (optional if using Docker)"
    WARNINGS=$((WARNINGS + 1))
fi

if [ -f "requirements.txt" ]; then
    echo "✅ requirements.txt exists"
else
    echo "❌ requirements.txt missing"
    ERRORS=$((ERRORS + 1))
fi

# Check Dockerfile content
echo ""
echo "Checking Dockerfile content..."
if [ -f "Dockerfile" ]; then
    if grep -q "tesseract-ocr" Dockerfile; then
        echo "✅ Dockerfile includes Tesseract OCR"
    else
        echo "❌ Dockerfile missing Tesseract OCR installation"
        ERRORS=$((ERRORS + 1))
    fi
    
    if grep -q "requirements.txt" Dockerfile; then
        echo "✅ Dockerfile includes requirements.txt"
    else
        echo "❌ Dockerfile missing requirements.txt"
        ERRORS=$((ERRORS + 1))
    fi
fi

# Check render.yaml content
echo ""
echo "Checking render.yaml configuration..."
if [ -f "render.yaml" ]; then
    if grep -q "type: web" render.yaml; then
        echo "✅ render.yaml has web service configuration"
    else
        echo "⚠️  render.yaml missing web service config"
        WARNINGS=$((WARNINGS + 1))
    fi
    
    if grep -q "env: docker" render.yaml || grep -q "dockerfilePath" render.yaml; then
        echo "✅ render.yaml configured for Docker"
    else
        echo "⚠️  render.yaml not configured for Docker"
        WARNINGS=$((WARNINGS + 1))
    fi
fi

# Check git status
echo ""
echo "Checking git status..."
if [ -d ".git" ]; then
    if [ -n "$(git status --porcelain)" ]; then
        echo "⚠️  You have uncommitted changes"
        echo "   Run: git add . && git commit -m 'Prepare for deployment'"
        WARNINGS=$((WARNINGS + 1))
    else
        echo "✅ All changes committed"
    fi
    
    REMOTE=$(git remote get-url origin 2>/dev/null)
    if [ -n "$REMOTE" ]; then
        echo "✅ Git remote configured: $REMOTE"
    else
        echo "⚠️  No git remote configured"
        WARNINGS=$((WARNINGS + 1))
    fi
else
    echo "⚠️  Not a git repository"
    WARNINGS=$((WARNINGS + 1))
fi

# Summary
echo ""
echo "=========================================="
echo "Summary"
echo "=========================================="
echo "Errors: $ERRORS"
echo "Warnings: $WARNINGS"
echo ""

if [ $ERRORS -eq 0 ]; then
    echo "✅ Project is ready for deployment!"
    echo ""
    echo "Next steps:"
    echo "1. Push to GitHub: git push origin main"
    echo "2. Go to Render Dashboard → New Web Service"
    echo "3. Connect your GitHub repository"
    echo "4. Render will auto-detect render.yaml and Dockerfile"
    exit 0
else
    echo "❌ Please fix the errors above before deploying"
    exit 1
fi

