# OmniScribe Desktop (PyQt + SQLite)

OmniScribe is a desktop app for converting lecture audio and supporting documents into transcripts, structured notes, and grounded AI chat answers.

## Recent Updates

- **In-app microphone recording**: New "Record" sub-tab lets you record audio directly from any available input device, with a live timer and device selector.
- Dynamic API health status in the sidebar (startup check + periodic checks).
- Attachment chips for audio/doc selections with remove actions.
- Audio attachment replacement confirmation and document selection deduplication.
- Staged progress indicator (spinner + stage label + elapsed time) during audio processing.
- Notes are rendered as Markdown (instead of raw Markdown text output).
- Chat source labels shown as separated chips and deduplicated.
- Improved RAG retrieval with better chunking, source diversity, and document weighting.
- Audio playback in the Transcripts view with a seek slider and time display.

## Current Capabilities

1. Upload one audio file and optional supporting documents in a single pipeline.
2. **Record audio directly in-app** using any available microphone, then transcribe with one click.
3. Transcribe audio with Groq Whisper and save both raw and corrected transcript versions.
4. Upload standalone documents and optionally link them to a selected audio session.
5. Generate notes from corrected transcripts in two modes:
   - Exact teacher wording
   - Reformulated student-friendly wording
6. Ask questions in AI Chat using RAG over corrected transcripts and extracted document text.
7. Play back any recorded or uploaded audio directly in the Transcripts view.
8. View API readiness status in-app (ready/loading/error).

## Tech Stack

- UI: PyQt6
- Database: SQLite
- API: Groq (OpenAI-compatible endpoints)
- Package manager: uv

## Project Structure

- `app/main.py` — application bootstrap and service wiring
- `app/config.py` — environment and path configuration
- `app/database.py` — SQLite schema and data access methods
- `app/services/groq_client.py` — Groq API wrappers (transcription, chat, health check)
- `app/services/api_status_service.py` — API availability status mapping for UI
- `app/services/transcription_service.py` — audio pipeline and transcript correction
- `app/services/document_service.py` — document storage and text extraction (PDF, DOCX, TXT/MD)
- `app/services/notes_service.py` — notes generation and persistence
- `app/services/rag_service.py` — retrieval and grounded answer generation
- `app/ui/main_window.py` — desktop UI
- `app/ui/workers.py` — background workers for non-blocking tasks
- `scripts/init_db.sql` — SQLite initialization script
- `.env.example` — environment variable template
- `run.py` — alternate run entrypoint

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

3. Configure required environment variables in `.env`:

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

### Upload flow
1. Open the **Audio** page and go to the **Upload** sub-tab.
2. Drop or browse for one audio file and optionally attach supporting documents.
3. Enter a lecture title, then click **Transcribe** and monitor staged progress.
4. Review raw and corrected transcripts in the **Transcripts** sub-tab, and play back the audio with the built-in player.

### Record flow
1. Open the **Audio** page and go to the **Record** sub-tab.
2. Select your microphone from the device dropdown.
3. Click **Start Recording**; a live timer shows elapsed time.
4. Click **Stop Recording**, then click **Transcribe** to process the recording.

### Documents & Notes
5. Upload additional documents from the **Documents** page and link them to an audio session if needed.
6. Generate notes in the selected note mode and view rendered Markdown output.

### AI Chat
7. Use **AI Chat** to ask grounded questions and review source chips for provenance.

## Data Stored

- Audio metadata and stored file path
- Raw transcript
- Corrected transcript
- Uploaded/recorded documents and extracted text
- Generated notes by mode

## Implementation Notes

- Long-running operations run in background worker threads to keep the UI responsive.
- Recording uses `QMediaRecorder` / `QMediaCaptureSession` with WAV output; the resulting file is fed directly into the normal transcription pipeline.
- API health checks run asynchronously at startup and every 20 seconds.
- RAG retrieval chunks transcripts/documents and selects diverse context chunks.
- Chat sources are deduplicated before display.