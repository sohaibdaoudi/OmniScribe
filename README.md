# OmniScribe MVP Desktop (PyQt + SQLite)

This repository contains a complete Phase 0 MVP desktop application using PyQt.

Implemented flow:

1. User uploads audio and optional documents.
2. Audio is sent to Groq Whisper for raw transcription.
3. Raw transcript is sent to Groq Llama 4 Scout for correction.
4. Both transcript versions are stored in SQLite.
5. User can upload standalone documents.
6. User can generate notes from corrected transcript in two modes:
   - Exact teacher wording
   - Reformulated version
7. User can ask questions in chat grounded on corrected transcripts and uploaded documents.

## Stack

- UI: PyQt6
- Database: SQLite
- API: Groq
  - Whisper transcription
  - Transcript correction
  - Notes generation
  - Chat response generation (RAG style with local retrieval)
- Package manager: uv

## Project Structure

- `app/main.py` - application bootstrap
- `app/config.py` - environment and path config
- `app/database.py` - SQLite schema + data access methods
- `app/services/groq_client.py` - Groq API wrappers
- `app/services/transcription_service.py` - audio upload and transcript correction pipeline
- `app/services/document_service.py` - document storage and text extraction (PDF/TXT/DOCX)
- `app/services/notes_service.py` - notes generation + persistence
- `app/services/rag_service.py` - simple retrieval + Groq grounded answer generation
- `app/ui/main_window.py` - desktop UI
- `app/ui/workers.py` - worker for background jobs
- `scripts/init_db.sql` - SQLite initialization script
- `.env.example` - required environment variables
- `run.py` - alternate run entrypoint

## Requirements

- Python 3.11+
- uv installed
- Groq API key

## Setup (uv)

1. Install dependencies:

```bash
uv sync
```

2. Create environment file:

```bash
cp .env.example .env
```

3. Set your key in `.env`:

```env
GROQ_API_KEY=your_groq_api_key_here
```

Optional model overrides:

```env
GROQ_WHISPER_MODEL=whisper-large-v3
GROQ_CHAT_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
```

## Run

```bash
uv run omniscribe
```

Alternatives:

```bash
uv run python run.py
uv run python -m app.main
```

## Database

The app auto-initializes SQLite on startup (`omniscribe.db` by default).

You can also initialize manually:

```bash
sqlite3 omniscribe.db < scripts/init_db.sql
```

Persisted entities:

- Audio metadata
- Raw transcript
- Corrected transcript
- Uploaded documents and extracted text
- Generated notes

## MVP User Flow

1. Open `Audio & Transcripts` tab.
2. Select audio and optional documents, then click `Upload + Transcribe`.
3. View raw and corrected transcripts.
4. Open `Documents` tab to upload extra files.
5. Open `Notes` tab to generate notes in selected mode.
6. Open `AI Chat` tab and ask questions against corrected transcripts + documents.

## Notes

- Long-running operations run in background worker threads to keep UI responsive.
- Retrieval is intentionally simple for MVP: local chunking + token overlap ranking.
- Chat answer generation is done by Groq using retrieved context.
