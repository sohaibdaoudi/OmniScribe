

## Where to start (step by step)

Don't try to build everything at once. Here's a logical order:

**Phase 1 — Core pipeline (weeks 1–3)**
Build just the upload + transcription flow first. A user uploads an audio file → you get back a transcript with timestamps. Nothing else. This validates your whole backend before you add complexity.

**Phase 2 — Documents + OCR (week 4)**
Add PDF upload and OCR for images. At this point you have audio + documents, but they're still separate.

**Phase 3 — LLM layer (weeks 5–6)**
Connect an LLM to do transcript cleanup, then notes/summaries/flashcards generation. This is where the product starts feeling real.

**Phase 4 — RAG / tutor (week 7–8)**
Add the vector database and build the Q&A chat. This is the most technically interesting part.

**Phase 5 — UI (throughout)**
Build the Next.js frontend in parallel as you have backend endpoints to call.

---

## Model & tool recommendations

**Speech-to-Text (ASR)**
Use **OpenAI Whisper** — specifically `whisper-large-v3`. It's free to run locally, handles accents and technical vocabulary well, and outputs word-level timestamps. If you want a hosted API to avoid managing a GPU, use **Deepgram Nova-2** (fast and cheap) or the **OpenAI Whisper API**.

**Speaker Diarization**
Use **pyannote.audio** (open source, runs locally). It requires a Hugging Face token and accepting their terms, but it's the best free option. Pair it with Whisper output to label who said what.

**OCR**
For printed text: **pdfplumber** or **PyMuPDF** for native PDFs (no OCR needed, just text extraction). For scanned documents and board photos: **Tesseract** (free, easy) or **PaddleOCR** (better accuracy on complex layouts). For very messy board photos, you can also send the image directly to a vision LLM (see below).

**LLM (for cleanup, notes, quizzes, Q&A)**
Use **Claude claude-sonnet-4-20250514** via the Anthropic API — it's excellent at structured outputs (JSON flashcards, outlines, etc.) and has a 200k context window which is ideal for long transcripts. For cost savings on simpler tasks (cleanup, short summaries), use **Claude Haiku**.

**Embeddings**
Use **text-embedding-3-small** from OpenAI — cheap, fast, and works well for English academic content. If you want fully local: **sentence-transformers/all-MiniLM-L6-v2**.

**Vector Database**
Start with **pgvector** (a PostgreSQL extension) — you already need PostgreSQL for your relational data, so this keeps things simple. Upgrade to **Qdrant** later if you need more advanced filtering.

---

## Database modelling (simplified)

Here are the key tables you need:

**`sessions`** — one row per lecture. Stores `id`, `title`, `created_at`, `status` (processing / ready), `audio_url`.

**`segments`** — the timestamped transcript. Each row = one spoken segment: `session_id`, `speaker_label`, `start_time`, `end_time`, `text`, `corrected_text`.

**`attachments`** — uploaded files linked to a session: `session_id`, `type` (pdf / image / scan), `file_url`, `extracted_text`, `page_count`.

**`chunks`** — for RAG. Each row = one searchable piece of content: `session_id`, `source_type` (transcript / attachment), `source_id` (foreign key to segment or attachment), `text`, `embedding` (vector column).

**`study_materials`** — generated outputs: `session_id`, `type` (summary / flashcard / quiz), `content` (JSON).

That's the core schema. You can add users/auth on top once the pipeline works.

---
