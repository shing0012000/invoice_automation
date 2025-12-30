# Invoice Automation Demo

A FastAPI-based invoice processing system that extracts accounting fields from invoice PDFs using rule-based extraction (no ML/AI).

## What This Demo Does

- **Upload Invoice PDFs**: Users can upload invoice PDFs through a web interface
- **Extract Fields**: Automatically extracts key accounting fields:
  - Invoice Number
  - Invoice Date
  - Vendor Name
  - Subtotal
  - Tax/VAT
  - Total Amount
  - Currency
- **Rule-Based Extraction**: Uses deterministic regex patterns and string heuristics (no machine learning)

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

4. **Deploy**
   - Render will automatically detect the `Procfile`
   - Build and deploy will start automatically
   - Service will be available at `https://your-app.onrender.com`

### Render Configuration

- **Build Command**: (auto-detected from Procfile)
- **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Environment**: Python 3
- **Plan**: Free tier works for demo

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | Database connection string (PostgreSQL or SQLite) | `postgresql+psycopg://postgres:postgres@localhost:5432/invoices` |
| `STORAGE_DIR` | Directory for storing uploaded files | `./storage` |
| `MAX_ATTEMPTS` | Maximum retry attempts for processing | `5` |
| `DEMO_MODE` | Enable demo mode (hides Swagger, exposes only demo endpoints) | `false` |
| `PORT` | Server port (Render sets this automatically) | `8000` |

## API Endpoints

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
│   └── extraction/
│       └── rule_based.py   # Rule-based field extraction
├── static/
│   └── demo.html            # Demo UI page
├── requirements.txt         # Python dependencies
├── Procfile                 # Render deployment config
├── docker-compose.yml       # PostgreSQL for local development
└── README.md               # This file
```

## How It Works

1. **Ingestion**: Invoice PDF is uploaded and stored
2. **OCR Simulation**: OCR text is generated (currently simulated)
3. **Extraction**: Rule-based extraction parses OCR text for accounting fields
4. **Response**: Extracted fields are returned to the user

## Technology Stack

- **FastAPI**: Web framework
- **SQLAlchemy**: ORM and database management
- **PostgreSQL/SQLite**: Database
- **Pydantic**: Data validation
- **Python 3.8+**: Runtime

## License

This is a demo project. Use at your own risk.

## Support

For issues or questions, please open an issue in the repository.

