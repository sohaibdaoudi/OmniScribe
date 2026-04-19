# OmniScribe Desktop (PyQt + SQLite)

OmniScribe is a desktop app for converting lecture audio and supporting documents into transcripts, structured notes, and grounded AI chat answers.

## Recent Updates

- Dynamic API health status in the sidebar (startup check + periodic checks).
- Attachment chips for audio/doc selections with remove actions.
- Audio attachment replacement confirmation and document selection deduplication.
- Determinate progress bar flow from 0% to 100% during audio processing.
- Notes are rendered as Markdown (instead of raw Markdown text output).
- Chat source labels shown as separated chips and deduplicated.
- Improved RAG retrieval with better chunking, source diversity, and document weighting.

## Current Capabilities

1. Upload one audio file and optional supporting documents in a single pipeline.
2. Transcribe audio with Groq Whisper and save both raw and corrected transcript versions.
3. Upload standalone documents and optionally link them to a selected audio session.
4. Generate notes from corrected transcripts in two modes:
  - Exact teacher wording
  - Reformulated student-friendly wording
5. Ask questions in AI Chat using RAG over corrected transcripts and extracted document text.
6. View API readiness status in-app (ready/loading/error).

## Tech Stack

- UI: PyQt6
- Database: SQLite
- API: Groq (OpenAI-compatible endpoints)
- Package manager: uv

## Project Structure

- app/main.py: application bootstrap and service wiring
- app/config.py: environment and path configuration
- app/database.py: SQLite schema and data access methods
- app/services/groq_client.py: Groq API wrappers (transcription, chat, health check)
- app/services/api_status_service.py: API availability status mapping for UI
- app/services/transcription_service.py: audio pipeline and transcript correction
- app/services/document_service.py: document storage and text extraction (PDF, DOCX, TXT/MD)
- app/services/notes_service.py: notes generation and persistence
- app/services/rag_service.py: retrieval and grounded answer generation
- app/ui/main_window.py: desktop UI
- app/ui/workers.py: background worker for non-blocking tasks
- scripts/init_db.sql: SQLite initialization script
- .env.example: environment variable template
- run.py: alternate run entrypoint

## Requirements

- Python 3.11+
- uv installed
- Groq API key

## Setup

1. Install dependencies:

```bash
uv sync
```

2. Create environment file:

```bash
cp .env.example .env
```

3. Configure required environment variables in .env:

```env
GROQ_API_KEY=your_groq_api_key_here
GROQ_WHISPER_MODEL=whisper-large-v3
GROQ_CHAT_MODEL=llama-3.3-70b-versatile
OMNISCRIBE_DB_PATH=omniscribe.db
OMNISCRIBE_STORAGE_DIR=storage
OMNISCRIBE_AUDIO_DIR=storage/audio
OMNISCRIBE_DOCUMENT_DIR=storage/documents
```

## Run

Preferred:

```bash
uv run omniscribe
```

Alternatives:

```bash
uv run run.py
uv run main.py
uv run python -m app.main
```

## User Flow

1. Open Audio and select one audio attachment.
2. Optionally attach supporting documents before transcription.
3. Click Transcribe and monitor staged progress from 0% to 100%.
4. Review raw and corrected transcripts in the transcripts view.
5. Upload additional documents from the Documents page and link to an audio session if needed.
6. Generate notes in the selected note mode and view rendered Markdown output.
7. Use AI Chat to ask grounded questions and review source chips for provenance.

## Data Stored

- Audio metadata and stored file path
- Raw transcript
- Corrected transcript
- Uploaded documents and extracted text
- Generated notes by mode

## Implementation Notes

- Long-running operations run in background worker threads to keep the UI responsive.
- API health checks run asynchronously at startup and every 20 seconds.
- RAG retrieval chunks transcripts/documents and selects diverse context chunks.
- Chat sources are deduplicated before display.
