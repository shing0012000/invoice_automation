#!/usr/bin/env python3
"""
Automated Render Deployment Script

This script uses Render's REST API to automatically:
1. Create a PostgreSQL database
2. Create a Web Service
3. Configure environment variables
4. Link the database to the service
5. Trigger deployment

Requirements:
- Render API key (get from: https://dashboard.render.com/account/api-keys)
- Python requests library: pip install requests
"""

import requests
import json
import sys
import os
from typing import Optional, Dict, Any

# Render API base URL
RENDER_API_BASE = "https://api.render.com/v1"

def get_api_key() -> Optional[str]:
    """Get Render API key from environment or prompt user."""
    api_key = os.getenv("RENDER_API_KEY")
    if not api_key:
        print("\n" + "="*60)
        print("Render API Key Required")
        print("="*60)
        print("To get your API key:")
        print("1. Go to: https://dashboard.render.com/account/api-keys")
        print("2. Click 'New API Key'")
        print("3. Copy the key")
        print("\nYou can either:")
        print("  - Set environment variable: export RENDER_API_KEY=your_key")
        print("  - Or enter it when prompted below")
        print("="*60)
        api_key = input("\nEnter your Render API key: ").strip()
    
    if not api_key:
        print("❌ API key is required. Exiting.")
        sys.exit(1)
    
    return api_key

def get_headers(api_key: str) -> Dict[str, str]:
    """Get request headers with API key."""
    return {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

def get_owner_id(api_key: str) -> Optional[str]:
    """Get the owner ID (user or team) for API requests."""
    headers = get_headers(api_key)
    response = requests.get(f"{RENDER_API_BASE}/owners", headers=headers)
    
    if response.status_code == 200:
        owners = response.json()
        if owners:
            # Use the first owner (usually the user)
            owner_id = owners[0].get("owner", {}).get("id")
            print(f"✅ Found owner ID: {owner_id}")
            return owner_id
        else:
            print("❌ No owners found")
            return None
    else:
        print(f"❌ Failed to get owner ID: {response.status_code} - {response.text}")
        return None

def create_postgres_database(api_key: str, owner_id: str, name: str = "invoice-automation-db") -> Optional[str]:
    """Create a PostgreSQL database on Render."""
    print(f"\n📦 Creating PostgreSQL database: {name}...")
    
    headers = get_headers(api_key)
    data = {
        "name": name,
        "databaseName": "invoices",
        "user": "invoice_user",
        "plan": "free",  # or "starter", "standard", etc.
        "region": "oregon"  # or your preferred region
    }
    
    response = requests.post(
        f"{RENDER_API_BASE}/owners/{owner_id}/databases",
        headers=headers,
        json=data
    )
    
    if response.status_code == 201:
        db = response.json()
        db_id = db.get("database", {}).get("id")
        connection_string = db.get("database", {}).get("connectionString")
        print(f"✅ Database created: {db_id}")
        print(f"   Connection string: {connection_string[:50]}...")
        return db_id
    else:
        print(f"❌ Failed to create database: {response.status_code} - {response.text}")
        return None

def get_repo_info() -> Dict[str, str]:
    """Get repository information from git."""
    import subprocess
    
    try:
        # Get remote URL
        remote_url = subprocess.check_output(
            ["git", "config", "--get", "remote.origin.url"],
            text=True
        ).strip()
        
        # Extract owner and repo name
        # Handle both https://github.com/owner/repo.git and git@github.com:owner/repo.git
        if "github.com" in remote_url:
            parts = remote_url.replace(".git", "").split("/")
            repo_name = parts[-1]
            owner = parts[-2] if len(parts) > 1 else None
            
            return {
                "repo": f"{owner}/{repo_name}",
                "owner": owner,
                "name": repo_name
            }
    except Exception as e:
        print(f"⚠️  Could not get git repo info: {e}")
    
    return {
        "repo": "shing0012000/invoice_automation",
        "owner": "shing0012000",
        "name": "invoice_automation"
    }

def create_web_service(api_key: str, owner_id: str, db_id: Optional[str] = None) -> Optional[str]:
    """Create a Web Service on Render."""
    print(f"\n🚀 Creating Web Service...")
    
    repo_info = get_repo_info()
    print(f"   Repository: {repo_info['repo']}")
    
    headers = get_headers(api_key)
    
    # Build service configuration
    service_data = {
        "type": "web_service",
        "name": "invoice-automation",
        "repo": repo_info["repo"],
        "branch": "main",
        "rootDir": "invoice_automation",
        "runtime": "docker",  # Use Docker for Tesseract OCR
        "plan": "free",
        "region": "oregon",
        "healthCheckPath": "/health",
        "envVars": [
            {
                "key": "DEMO_MODE",
                "value": "true"
            },
            {
                "key": "ENABLE_LEVEL_3_EXTRACTION",
                "value": "false"
            },
            {
                "key": "ENABLE_SEMANTIC_EXTRACTION",
                "value": "false"
            },
            {
                "key": "USE_LLM_FALLBACK",
                "value": "true"
            },
            {
                "key": "MIN_EXTRACTION_RATE",
                "value": "0.5"
            },
            {
                "key": "STORAGE_DIR",
                "value": "./storage"
            }
        ]
    }
    
    # Add database connection if database was created
    if db_id:
        service_data["envVars"].append({
            "key": "DATABASE_URL",
            "value": f"${{db.{db_id}.DATABASE_URL}}"  # Reference the database
        })
    
    response = requests.post(
        f"{RENDER_API_BASE}/owners/{owner_id}/services",
        headers=headers,
        json=service_data
    )
    
    if response.status_code == 201:
        service = response.json()
        service_id = service.get("service", {}).get("id")
        service_url = service.get("service", {}).get("serviceDetails", {}).get("url")
        print(f"✅ Web Service created: {service_id}")
        if service_url:
            print(f"   URL: {service_url}")
        return service_id
    else:
        print(f"❌ Failed to create service: {response.status_code} - {response.text}")
        print(f"   Response: {json.dumps(response.json(), indent=2)}")
        return None

def main():
    """Main deployment function."""
    print("="*60)
    print("Automated Render Deployment")
    print("="*60)
    
    # Get API key
    api_key = get_api_key()
    
    # Get owner ID
    print("\n🔍 Getting owner information...")
    owner_id = get_owner_id(api_key)
    if not owner_id:
        print("❌ Could not get owner ID. Exiting.")
        sys.exit(1)
    
    # Ask user what to create
    print("\n" + "="*60)
    print("What would you like to create?")
    print("="*60)
    print("1. Create PostgreSQL database + Web Service (recommended)")
    print("2. Create Web Service only (use existing database)")
    print("3. Create PostgreSQL database only")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    db_id = None
    service_id = None
    
    if choice == "1" or choice == "3":
        # Create database
        db_name = input("Database name (default: invoice-automation-db): ").strip() or "invoice-automation-db"
        db_id = create_postgres_database(api_key, owner_id, db_name)
        if not db_id and choice == "1":
            print("❌ Database creation failed. Cannot continue with service creation.")
            sys.exit(1)
    
    if choice == "1" or choice == "2":
        # Create web service
        service_id = create_web_service(api_key, owner_id, db_id)
        if not service_id:
            print("❌ Service creation failed.")
            sys.exit(1)
    
    # Summary
    print("\n" + "="*60)
    print("✅ Deployment Complete!")
    print("="*60)
    if db_id:
        print(f"📦 Database ID: {db_id}")
    if service_id:
        print(f"🚀 Service ID: {service_id}")
    print("\nNext steps:")
    print("1. Check Render Dashboard: https://dashboard.render.com")
    print("2. Wait for deployment to complete (usually 2-5 minutes)")
    print("3. Test your service at the URL shown in Render Dashboard")
    print("4. If using Gemini, add GOOGLE_API_KEY in Render Dashboard → Environment")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Deployment cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

