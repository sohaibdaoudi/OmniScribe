from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS audios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transcripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audio_id INTEGER NOT NULL UNIQUE,
    raw_text TEXT NOT NULL,
    corrected_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(audio_id) REFERENCES audios(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audio_id INTEGER NULL,
    original_filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    extracted_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(audio_id) REFERENCES audios(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audio_id INTEGER NOT NULL,
    mode TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(audio_id) REFERENCES audios(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS quizzes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audio_id INTEGER NOT NULL,
    num_questions INTEGER NOT NULL,
    focus TEXT NULL,
    difficulty TEXT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(audio_id) REFERENCES audios(id) ON DELETE CASCADE
);
"""


class Database:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        return connection

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(SCHEMA_SQL)
            connection.commit()

    def add_audio(self, title: str, original_filename: str, stored_path: str) -> int:
        query = """
        INSERT INTO audios (title, original_filename, stored_path)
        VALUES (?, ?, ?)
        """
        with self._connect() as connection:
            cursor = connection.execute(query, (title, original_filename, stored_path))
            connection.commit()
            return int(cursor.lastrowid)

    def list_audios(self) -> list[dict[str, Any]]:
        query = """
        SELECT
            a.id,
            a.title,
            a.original_filename,
            a.stored_path,
            a.created_at,
            CASE WHEN t.id IS NULL THEN 0 ELSE 1 END AS has_transcript
        FROM audios a
        LEFT JOIN transcripts t ON t.audio_id = a.id
        ORDER BY a.created_at DESC, a.id DESC
        """
        with self._connect() as connection:
            rows = connection.execute(query).fetchall()
        return [dict(row) for row in rows]

    def save_transcript(self, audio_id: int, raw_text: str, corrected_text: str) -> None:
        query = """
        INSERT INTO transcripts (audio_id, raw_text, corrected_text)
        VALUES (?, ?, ?)
        ON CONFLICT(audio_id) DO UPDATE SET
            raw_text = excluded.raw_text,
            corrected_text = excluded.corrected_text,
            created_at = CURRENT_TIMESTAMP
        """
        with self._connect() as connection:
            connection.execute(query, (audio_id, raw_text, corrected_text))
            connection.commit()

    def get_transcript_by_audio(self, audio_id: int) -> dict[str, Any] | None:
        query = """
        SELECT id, audio_id, raw_text, corrected_text, created_at
        FROM transcripts
        WHERE audio_id = ?
        """
        with self._connect() as connection:
            row = connection.execute(query, (audio_id,)).fetchone()
        return dict(row) if row else None

    def add_document(
        self,
        original_filename: str,
        stored_path: str,
        extracted_text: str,
        audio_id: int | None = None,
    ) -> int:
        query = """
        INSERT INTO documents (audio_id, original_filename, stored_path, extracted_text)
        VALUES (?, ?, ?, ?)
        """
        with self._connect() as connection:
            cursor = connection.execute(query, (audio_id, original_filename, stored_path, extracted_text))
            connection.commit()
            return int(cursor.lastrowid)

    def list_documents(self, audio_id: int | None = None) -> list[dict[str, Any]]:
        base_query = """
        SELECT
            d.id,
            d.audio_id,
            d.original_filename,
            d.stored_path,
            d.extracted_text,
            d.created_at,
            a.title AS audio_title
        FROM documents d
        LEFT JOIN audios a ON a.id = d.audio_id
        """
        params: tuple[Any, ...] = ()
        if audio_id is not None:
            base_query += " WHERE d.audio_id = ?"
            params = (audio_id,)

        base_query += " ORDER BY d.created_at DESC, d.id DESC"

        with self._connect() as connection:
            rows = connection.execute(base_query, params).fetchall()
        return [dict(row) for row in rows]

    def add_note(self, audio_id: int, mode: str, content: str) -> int:
        query = """
        INSERT INTO notes (audio_id, mode, content)
        VALUES (?, ?, ?)
        """
        with self._connect() as connection:
            cursor = connection.execute(query, (audio_id, mode, content))
            connection.commit()
            return int(cursor.lastrowid)

    def add_quiz(
        self,
        *,
        audio_id: int,
        num_questions: int,
        focus: str | None,
        difficulty: str | None,
        content: str,
    ) -> int:
        query = """
        INSERT INTO quizzes (audio_id, num_questions, focus, difficulty, content)
        VALUES (?, ?, ?, ?, ?)
        """
        with self._connect() as connection:
            cursor = connection.execute(
                query, (audio_id, num_questions, focus, difficulty, content)
            )
            connection.commit()
            return int(cursor.lastrowid)

    def get_latest_note(self, audio_id: int, mode: str | None = None) -> dict[str, Any] | None:
        query = """
        SELECT id, audio_id, mode, content, created_at
        FROM notes
        WHERE audio_id = ?
        """
        params: list[Any] = [audio_id]
        if mode is not None:
            query += " AND mode = ?"
            params.append(mode)

        query += " ORDER BY created_at DESC, id DESC LIMIT 1"

        with self._connect() as connection:
            row = connection.execute(query, tuple(params)).fetchone()
        return dict(row) if row else None

    def get_latest_quiz(
        self,
        *,
        audio_id: int,
        difficulty: str | None = None,
        num_questions: int | None = None,
    ) -> dict[str, Any] | None:
        query = """
        SELECT id, audio_id, num_questions, focus, difficulty, content, created_at
        FROM quizzes
        WHERE audio_id = ?
        """
        params: list[Any] = [audio_id]

        if difficulty is not None:
            query += " AND difficulty = ?"
            params.append(difficulty)
        if num_questions is not None:
            query += " AND num_questions = ?"
            params.append(num_questions)

        query += " ORDER BY created_at DESC, id DESC LIMIT 1"
        with self._connect() as connection:
            row = connection.execute(query, tuple(params)).fetchone()
        return dict(row) if row else None

    def get_corrected_transcripts(self, audio_id: int | None = None) -> list[dict[str, Any]]:
        query = """
        SELECT
            t.id,
            t.audio_id,
            t.corrected_text,
            t.created_at,
            a.title AS audio_title
        FROM transcripts t
        INNER JOIN audios a ON a.id = t.audio_id
        WHERE t.corrected_text != ''
        """
        params: tuple[Any, ...] = ()
        if audio_id is not None:
            query += " AND t.audio_id = ?"
            params = (audio_id,)

        query += " ORDER BY t.created_at DESC, t.id DESC"

        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]
