# Medical RAG System

AI-powered medical consultation system using Agentic RAG (Retrieval-Augmented Generation) with LangGraph agents.

## Tech Stack

- **Frontend**: Angular 20 standalone + TypeScript + PrimeNG + ngx-markdown + Chart.js
- **Backend**: Python + FastAPI + LangGraph + LangChain
- **Database**: PostgreSQL
- **Vector DB**: Qdrant
- **LLM / Embedding**: Google Gemini API

## Current Scope

The current codebase includes these main product areas:

- User authentication with JWT access and refresh tokens
- Medical chat with streaming SSE responses
- Retrieval-augmented generation from medical documents stored in Qdrant
- Consultation history and session detail views
- Health dashboard and timeline analysis
- Wallet / reward flow:
  - point balance
  - daily check-in
  - promo code redemption
- Weather-based health risk endpoint and frontend card

## Project Structure

```text
medical-rag/
|-- backend/                  # FastAPI backend
|   |-- app/
|   |   |-- agents/           # LangGraph medical pipeline
|   |   |-- api/routes/       # FastAPI routes
|   |   |-- core/             # Config, prompts, security, limiter
|   |   |-- db/               # SQLAlchemy session and ORM models
|   |   |-- models/           # Pydantic schemas
|   |   |-- services/         # Business logic
|   |   `-- utils/            # Shared helpers
|   |-- scripts/              # Ingestion / test scripts
|   |-- tests/                # Backend tests
|   `-- main.py               # FastAPI entrypoint
|-- frontend/                 # Angular frontend
|   |-- src/
|   |   |-- app/
|   |   |   |-- core/         # Services, guard, interceptor, models
|   |   |   |-- features/     # Auth, chat, history, analysis, wallet
|   |   |   `-- shared/       # Navbar, wallet widget, pipe
|   |   |-- environments/
|   |   |-- index.html
|   |   |-- main.ts
|   |   `-- styles.scss
|   `-- public/               # Static assets
|-- docker-compose.yml
|-- .env.example
|-- PROJECT_OVERVIEW.md
`-- README.md
```

## Ports

### Local development

- Frontend: `http://localhost:4000`
- Backend: `http://localhost:8000`
- Qdrant: `http://localhost:6333`

### Docker Compose

- Frontend: `http://localhost:4000`
- Backend: `http://localhost:8000`
- Qdrant: `http://localhost:6333`

The frontend Docker container now runs Angular on port `4000` and binds to `0.0.0.0`, which matches `docker-compose.yml`.

## Installation & Setup

### Prerequisites

- Docker and Docker Compose
- Python 3.10+
- Node.js 18+
- A valid `GOOGLE_API_KEY`

### 1. Prepare environment

```bash
git clone <repository-url>
cd medical-rag
cp .env.example .env
```

Then fill in the required environment variables in `.env`.

### 2. Start with Docker Compose

```bash
docker-compose up --build
```

This starts:

- Qdrant on `6333`
- FastAPI backend on `8000`
- Angular frontend on `4000`

### 3. Local development

#### Backend

```bash
cd backend
pip install poetry
poetry install
poetry run uvicorn main:app --reload
```

#### Frontend

```bash
cd frontend
npm install
npm start
```

#### Qdrant

```bash
docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant
```

## Usage

1. Open the frontend at `http://localhost:4000`
2. Use the backend API at `http://localhost:8000`
3. Visit FastAPI docs at `http://localhost:8000/docs`
4. Ingest medical PDFs with:

```bash
python backend/scripts/ingest_pdf.py path/to/document.pdf
```

## Development Notes

- Frontend uses Angular standalone components, not React.
- Frontend auth tokens are currently stored in `sessionStorage`.
- Chat responses are streamed with `fetch + ReadableStream` using SSE payloads.
- Some legacy methods still exist in the frontend `ApiService`; not every helper maps cleanly to a live backend route.

## Test Commands

- Backend tests: `cd backend && poetry run pytest`
- Frontend tests: `cd frontend && npm test`

## License

