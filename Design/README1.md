# OmniScribe — Multimodal Lecture Intelligence Assistant

OmniScribe is a student-first AI assistant that captures lectures in real time (or from uploaded audio), fuses them with slides/handouts/board photos, and turns everything into a searchable, citeable knowledge base that can generate study materials and act as an interactive tutor.

Unlike “transcribe + summarize” tools, OmniScribe treats a lecture as a **timeline**: speech segments, speakers, and visual artifacts (slides/board photos) are linked to timestamps so students can review *exactly what was said when a slide or diagram was shown*.

---

## Problem Statement
Students struggle to create accurate notes while listening and understanding in real time. Recordings help, but:

- Transcripts contain errors (names, formulas, jargon).
- Slides/board content is disconnected from what was said.
- Searching recordings is slow and imprecise.
- Study prep (flashcards/quizzes/revision) requires extra work.

---

## Solution Overview
OmniScribe ingests **audio + documents + images**, produces a timestamped, speaker-labeled transcript, runs LLM-based cleanup and structuring, indexes content into a vector knowledge base, and exposes:

- a RAG-powered tutor/chat experience (grounded in your lecture content)
- automatic study material generation (summaries, notes, flashcards, quizzes)
- a review UI that links transcript segments to slides/board photos

---

## Key Features

### Lecture Capture
- Real-time recording with live transcription (WebSocket streaming)
- Upload audio for batch processing (no live session required)
- Timeline view: transcript segments aligned with lecture time

### Speaker Diarization
- Separates and labels speakers (e.g., Professor vs Student)
- Produces structured output: speaker, timestamps, text

### Multimodal Attachments
- Upload PDFs and slide decks (before or after the lecture)
- Upload scanned documents and handwritten notes (before or after the lecture)
- Capture board/slide photos during class and attach them to timestamps
- Post-lecture enrichment: attach extra materials later (e.g., a friend’s notes) and re-run indexing/study generation

### OCR + Parsing
- If document is text-based: extract text directly
- If scanned/image-based: OCR to recover text + layout signals
- Extracts key text from board photos and slide screenshots

### Transcription Correction (LLM-Assisted)
- Cleans disfluencies, fixes obvious ASR errors
- Uses course vocabulary (glossary) and visual text (OCR) as “context hints”
- Produces a corrected transcript while preserving timestamps

### Study Material Generation
- Lecture summaries (short + long)
- Structured notes (outline with headings)
- Key takeaways and definitions
- Flashcards and quizzes
- Exam revision packs (topic-wise)

### AI Tutor / Study Coach
- Q&A grounded in lecture + attachments (RAG)
- Explanations at different difficulty levels
- Quiz mode: generate questions, grade answers, suggest weak areas

### Semantic Search
- Ask natural-language questions across all your lectures/materials
- Retrieves relevant snippets with citations back to the transcript segment / page / image

---

## System Architecture

### High-Level Data Flow

1) **Session creation & ingestion**
- Create a lecture session from live recording **or** from uploaded audio
- Add documents/images either upfront **or later** (post-lecture enrichment)

2) **Speech processing**
- Speech-to-Text (ASR)
- Speaker diarization
- Timestamped segment assembly

3) **Visual/document processing**
- PDF text extraction OR OCR for scans/images
- Optional vision-language extraction for layout-heavy pages (tables/figures)

4) **Fusion layer**
- Attachments mapped to the lecture (and optionally to timestamp events)
- Optional alignment: correlate transcript segments with slide/page text
- Re-index on new attachments so search/tutor/study outputs stay up to date

5) **LLM processing**
- Transcript cleanup/correction (with guardrails)
- Note structuring + summarization
- Quiz/flashcard generation

6) **Indexing & storage**
- Chunking + embeddings
- Vector DB for semantic retrieval
- Relational DB for metadata + timeline
- Object storage for raw media

7) **Applications**
- RAG tutor/chat
- Study material exports
- Search + review UI

---

## Technology Stack (Realistic Defaults)

### Frontend
- Next.js (React) for the web app
- WebAudio APIs for recording
- WebSockets for live transcript streaming

### Backend
- FastAPI (Python) for APIs and orchestration
- Background jobs (e.g., Celery/RQ or a managed queue) for long-running processing

### Speech
- ASR: Whisper (local) or a hosted speech API
- Diarization: diarization model/service (choose based on licensing and deployment constraints)

### OCR / Document Processing
- Text PDFs: PDF text extraction
- Scans/images: Tesseract or PaddleOCR
- Optional: a vision-language model/API for robust layout understanding

### LLM + Orchestration
- Any strong LLM (cloud or local) behind a single interface
- Prompting with structured outputs (JSON) validated via schemas

### Retrieval
- Embeddings model suitable for your language domain
- Vector DB: Qdrant, pgvector, or a managed vector store

### Storage
- Relational DB (PostgreSQL) for sessions, metadata, and permissions
- Object storage (S3-compatible) for audio/images/PDFs

---

## AI Components (What Each Module Does)

- **ASR (Speech-to-Text)**: converts audio to a timestamped transcript.
- **Diarization**: assigns speaker labels to segments.
- **OCR / Parsing**: extracts text from scans, images, and board photos.
- **Transcript Correction (LLM)**: reduces ASR errors and normalizes text while preserving timing.
- **Chunking + Embeddings**: converts content into retrievable semantic vectors.
- **RAG Tutor**: retrieves relevant chunks and answers strictly from lecture sources.
- **Study Generator**: produces notes, flashcards, quizzes, and revision packs from grounded lecture content.

---

## Example Use Case
During a Machine Learning lecture:

1. A student starts live recording.
2. OmniScribe displays a live transcript.
3. The student snaps photos of the board when formulas appear; each photo is timestamped.
4. After class, the student uploads a scanned handwritten summary from a friend and a PDF handout.
5. OmniScribe re-processes the session (OCR + indexing) and generates:
   - a structured outline of the lecture
   - a summary + key takeaways
   - flashcards for key definitions
   - a quiz focused on the professor’s emphasized points
6. The student asks the tutor: “Explain the bias–variance tradeoff from today,” and gets an answer with citations pointing to the exact transcript segment and related board photo.

Offline / upload-only workflow:

1. The student uploads a previously recorded audio file plus scanned notes and slides.
2. OmniScribe processes everything as a single lecture session and provides search, tutor Q&A, and generated study materials.

---

## Future Improvements
- Stronger multimodal alignment (slide/page ↔ transcript segment matching)
- Real-time “concept alerts” (detect confusion points and suggest clarifications)
- Collaborative study rooms (shared sessions, annotations)
- Offline-first mode for privacy-sensitive environments
- Knowledge graph extraction for prerequisites and concept relationships
- Evaluation suite: WER tracking, retrieval metrics, and user-feedback learning loops

---

## Why This Project Is Innovative
- Treats learning as a **multimodal, timestamped timeline**, not just text.
- Fuses **audio + documents + images** into one grounded knowledge base.
- Combines production-grade concerns: streaming, async pipelines, indexing, citations, and UI review loops.
- Demonstrates modern AI engineering: ASR + diarization + OCR + LLM structuring + RAG.
