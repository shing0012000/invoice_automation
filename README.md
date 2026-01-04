# Invoice Automation Demo

A FastAPI-based invoice processing system that extracts accounting fields from invoice PDFs using a **multi-level extraction pipeline** (Level 1: OCR, Level 2: Structural Parser, Level 3: Semantic Extractor).

## What This Demo Does

- **Upload Invoice Files**: Users can upload invoice PDFs or images (PNG, JPEG, TIFF) through a web interface
- **Extract Fields**: Automatically extracts key accounting fields:
  - Invoice Number
  - Invoice Date
  - Vendor Name
  - Subtotal
  - Tax/VAT
  - Total Amount
  - Currency
- **Multi-Level Extraction**: Uses three levels of extraction with intelligent fallback:
  - **Level 1 (OCR)**: Basic text extraction from PDFs and images
  - **Level 1.5 (Rule-Based)**: Regex patterns and string heuristics (always enabled)
  - **Level 2 (Structural)**: Understands geometry, tables, and layout (enabled by default, works best with PDFs)
  - **Level 3 (Semantic)**: ML/LLM-based semantic understanding (optional, requires API keys)

## Demo Limitations

⚠️ **This is a demonstration system:**
- No permanent data storage guarantee
- Best-effort processing only
- No authentication or user accounts
- Data may be cleared periodically
- Not suitable for production use

## Running Locally

### Prerequisites

- Python 3.8+
- pip

### Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd invoice_automation
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment** (optional)
   ```bash
   # Copy example env file
   cp .env.example .env
   
   # Edit .env with your settings:
   # - DATABASE_URL (use sqlite:///./invoice_demo.db for local demo)
   # - DEMO_MODE=true (to enable demo mode)
   ```

4. **Run the application**
   ```bash
   # Using uvicorn directly
   uvicorn app.main:app --reload
   
   # Or using the Procfile (requires foreman/honcho)
   foreman start
   ```

5. **Access the demo**
   - Open http://localhost:8000 in your browser
   - Upload an invoice PDF
   - View extracted fields

### Local Development (with PostgreSQL)

If you want to use PostgreSQL locally:

1. **Start PostgreSQL** (using Docker)
   ```bash
   docker-compose up -d
   ```

2. **Set DATABASE_URL** in `.env`:
   ```
   DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/invoices
   ```

3. **Run the application**
   ```bash
   uvicorn app.main:app --reload
   ```

## Deployment to Render

### Prerequisites

- Render account (free tier works)
- GitHub repository with this code

### Steps

1. **Push to GitHub**
   ```bash
   git add .
   git commit -m "Prepare for Render deployment"
   git push origin main
   ```

2. **Create Render Web Service**
   - Go to [Render Dashboard](https://dashboard.render.com)
   - Click "New +" → "Web Service"
   - Connect your GitHub repository
   - Select the `invoice_automation` directory

3. **Configure Environment Variables**
   ```
   DATABASE_URL=sqlite:///./invoice_demo.db
   DEMO_MODE=true
   PORT=8000
   ```
   Note: `PORT` is automatically set by Render - you don't need to set it manually.

4. **Configure Health Check** (Important!)
   - In Render dashboard, go to your service settings
   - Under "Health Check Path", set: `/health`
   - This prevents deployment timeouts

5. **Deploy**
   - Render will automatically detect the `Procfile`
   - Build and deploy will start automatically
   - Service will be available at `https://your-app.onrender.com`

### Render Configuration

**Important**: To use Tesseract OCR on Render, you must set the build command:

- **Build Command**: `chmod +x build.sh && ./build.sh`
  - This installs Tesseract OCR system package (`tesseract-ocr` and `tesseract-ocr-eng`)
  - Then installs all Python dependencies from `requirements.txt`
  - The `build.sh` script handles everything automatically
  
- **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Environment**: Python 3
- **Plan**: Free tier works for demo

**How to Configure**:
1. In Render Dashboard → Your Service → Settings
2. Under "Build Command", set: `chmod +x build.sh && ./build.sh`
3. Save and redeploy

**Alternative**: If you use `render.yaml`, Render will automatically use the build command specified there.

**Note**: Without the build script, Tesseract OCR won't be available and image extraction will fail. The build script is required for Tesseract OCR on Render.

## Multi-Level Extraction System

This system uses a three-level extraction pipeline inspired by Google Document AI:

### Level 1: Basic OCR
- Extracts raw text from PDFs using `pdfplumber` and `PyPDF2`
- Handles text-based PDFs (not scanned images)
- Always enabled

### Level 1.5: Rule-Based Extraction
- Uses regex patterns and string heuristics
- Deterministic and explainable
- Always enabled as baseline fallback

### Level 2: Structural Parser (Document AI OCR/Form Parser equivalent)
- **Understands geometry**: Uses bounding boxes (X, Y coordinates) of words
- **Recognizes layout**: Identifies tables, form fields, and spatial relationships
- **Table-aware**: Extracts data from structured tables, not just text patterns
- **Enabled by default** (set `ENABLE_LEVEL_2_EXTRACTION=false` to disable)

**Key Features:**
- Processes tables as structured data
- Understands spatial relationships (e.g., "Total" near a number = total amount)
- Layout-aware extraction (finds fields regardless of position)

### Level 3: Semantic Extractor (Document AI Specialized/GenAI equivalent)
- **Semantic understanding**: Understands meaning, not just patterns
- **Layout-agnostic**: Finds "Total" whether it's at top, bottom, or in a table
- **Context-aware**: Distinguishes "Billing Address" from "Shipping Address" even if unlabeled
- **Requires API keys** (OpenAI or Google Document AI)
- **Disabled by default** (set `ENABLE_LEVEL_3_EXTRACTION=true` and configure API keys)

**Supported Services:**
- **OpenAI GPT**: Set `OPENAI_API_KEY` and `OPENAI_MODEL` (default: `gpt-3.5-turbo`)
- **Google Document AI**: Set `GOOGLE_APPLICATION_CREDENTIALS`, `GOOGLE_CLOUD_PROJECT_ID`, and `GOOGLE_DOCUMENT_AI_PROCESSOR_ID`

**How It Works:**
1. Pipeline tries Level 1.5 (rule-based) first
2. Then Level 2 (structural) if enabled - overrides rule-based results
3. Finally Level 3 (semantic) if enabled - overrides all lower levels
4. Results are merged intelligently (higher levels take precedence)

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | Database connection string (PostgreSQL or SQLite) | `postgresql+psycopg://postgres:postgres@localhost:5432/invoices` |
| `STORAGE_DIR` | Directory for storing uploaded files | `./storage` |
| `MAX_ATTEMPTS` | Maximum retry attempts for processing | `5` |
| `DEMO_MODE` | Enable demo mode (hides Swagger, exposes only demo endpoints) | `false` |
| `PORT` | Server port (Render sets this automatically) | `8000` |
| `ENABLE_LEVEL_2_EXTRACTION` | Enable Level 2 (Structural Parser) | `true` |
| `ENABLE_LEVEL_3_EXTRACTION` | Enable Level 3 (Semantic Extractor) | `false` |
| `ENABLE_SEMANTIC_EXTRACTION` | Enable semantic extraction (required for Level 3) | `false` |
| `OPENAI_API_KEY` | OpenAI API key for Level 3 extraction (optional) | - |
| `OPENAI_MODEL` | OpenAI model to use (e.g., `gpt-3.5-turbo`, `gpt-4`) | `gpt-3.5-turbo` |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to Google Cloud credentials JSON (optional) | - |
| `GOOGLE_CLOUD_PROJECT_ID` | Google Cloud project ID (optional) | - |
| `GOOGLE_DOCUMENT_AI_PROCESSOR_ID` | Document AI processor ID (optional) | - |
| `GOOGLE_CLOUD_LOCATION` | Google Cloud location (optional) | `us` |

## API Endpoints

### Health Check (Always Available)

- `GET /health` - Health check endpoint for cloud platforms
  - Returns: `{"status": "healthy", "service": "invoice-automation", "database": "connected", "demo_mode": true}`
  - Used by Render, Fly.io, Railway for deployment verification

### Demo Mode (when `DEMO_MODE=true`)

- `GET /` - Demo UI (HTML page)
- `POST /demo/upload-invoice` - Upload invoice and get extracted fields

### Development Mode (when `DEMO_MODE=false`)

- `GET /` - Demo UI
- `GET /docs` - Swagger UI documentation
- `POST /ingest/email-attachment` - Internal ingestion endpoint
- `GET /invoices/{invoice_id}` - Get invoice details
- `POST /demo/upload-invoice` - Demo endpoint

## Project Structure

```
invoice_automation/
├── app/
│   ├── main.py              # FastAPI application
│   ├── config.py            # Configuration settings
│   ├── db.py                # Database connection
│   ├── models.py            # SQLAlchemy models
│   ├── schemas.py           # Pydantic schemas
│   ├── crud.py              # Database operations
│   ├── worker.py            # Background worker functions
│   ├── pdf_extraction.py     # Level 1: PDF text extraction
│   ├── image_extraction.py   # Level 1: Image OCR extraction
│   ├── text_extraction.py    # Unified text extraction (PDF + images)
│   └── extraction/
│       ├── rule_based.py     # Level 1.5: Rule-based field extraction
│       ├── structural.py     # Level 2: Structural parser (geometry, tables)
│       ├── semantic.py        # Level 3: Semantic extractor (ML/LLM)
│       └── pipeline.py        # Multi-level extraction orchestrator
├── static/
│   └── demo.html            # Demo UI page
├── requirements.txt         # Python dependencies
├── Procfile                 # Render deployment config
├── docker-compose.yml       # PostgreSQL for local development
└── README.md               # This file
```

## How It Works

1. **Ingestion**: Invoice file (PDF or image) is uploaded and stored
2. **Level 1 (OCR)**: Text is extracted from:
   - **PDF files**: Using `pdfplumber`/`PyPDF2`
   - **Image files**: Using Tesseract OCR (`pytesseract`) or EasyOCR (fallback)
3. **Multi-Level Extraction**: Pipeline extracts fields using:
   - Level 1.5: Rule-based patterns (always runs)
   - Level 2: Structural analysis (tables, geometry) - if enabled (works best with PDFs)
   - Level 3: Semantic understanding (ML/LLM) - if enabled and configured
4. **Response**: Extracted fields are merged and returned to the user

## Supported File Formats

### PDF Files
- Text-based PDFs (extracted directly)
- Scanned PDFs (may require OCR if text extraction fails)

### Image Files
- **PNG** (.png)
- **JPEG** (.jpg, .jpeg)
- **TIFF** (.tif, .tiff)
- **BMP** (.bmp)
- **GIF** (.gif)
- **WebP** (.webp)

Images are processed using OCR (Tesseract or EasyOCR) to extract text.

## Technology Stack

- **FastAPI**: Web framework
- **SQLAlchemy**: ORM and database management
- **PostgreSQL/SQLite**: Database
- **Pydantic**: Data validation
- **pdfplumber**: PDF text extraction and structural analysis
- **PyPDF2**: PDF text extraction (fallback)
- **Pillow**: Image processing
- **pytesseract**: OCR for images (requires Tesseract OCR system library)
- **EasyOCR** (optional): Alternative OCR library (no system dependencies)
- **OpenAI API** (optional): Level 3 semantic extraction
- **Google Document AI** (optional): Level 3 semantic extraction
- **Python 3.8+**: Runtime

## License

This is a demo project. Use at your own risk.

## Troubleshooting

### Render Deployment Timeout

If your deployment times out on Render:

1. **Check Health Check Path**: Ensure `/health` is set in Render dashboard
   - Go to your service → Settings → Health Check Path
   - Set to: `/health`

2. **Check Logs**: Look for startup errors in Render logs
   - Common issues: Database connection failures, missing environment variables

3. **Verify Environment Variables**: Ensure all required vars are set
   - `DATABASE_URL` must be valid
   - `DEMO_MODE` should be `true` for public demo

4. **Check Port**: Render sets `PORT` automatically - don't override it

### Database Connection Issues

- **SQLite**: Works out of the box, no setup needed
- **PostgreSQL**: Ensure connection string is correct
  - Format: `postgresql+psycopg://user:password@host:5432/dbname`
  - Check that database exists and credentials are correct

### Storage Directory Issues

- The app creates `./storage` directory automatically
- If creation fails, check file permissions
- On cloud platforms, ensure write access to working directory

## Support

For issues or questions, please open an issue in the repository.

