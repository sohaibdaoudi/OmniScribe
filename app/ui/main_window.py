from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt, QThread, QTimer
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.database import Database
from app.services.document_service import DocumentService
from app.services.notes_service import NOTE_MODE_EXACT, NOTE_MODE_REFORMULATED, NotesService
from app.services.rag_service import RagService
from app.services.transcription_service import TranscriptionService
from app.ui.workers import FunctionWorker


class MainWindow(QMainWindow):
    def __init__(
        self,
        database: Database,
        transcription_service: TranscriptionService,
        document_service: DocumentService,
        notes_service: NotesService,
        rag_service: RagService,
    ) -> None:
        super().__init__()
        self.database = database
        self.transcription_service = transcription_service
        self.document_service = document_service
        self.notes_service = notes_service
        self.rag_service = rag_service

        self._active_workers: list[tuple[QThread, FunctionWorker]] = []
        self._selected_audio_path: str | None = None
        self._selected_audio_documents: list[str] = []
        self._selected_document_paths: list[str] = []
        self._documents_cache: dict[int, dict[str, Any]] = {}

        self.setWindowTitle("OmniScribe MVP")
        self.resize(1200, 800)

        self._build_ui()
        self._refresh_all()

    def _build_ui(self) -> None:
        tabs = QTabWidget()
        tabs.addTab(self._build_audio_tab(), "Audio & Transcripts")
        tabs.addTab(self._build_documents_tab(), "Documents")
        tabs.addTab(self._build_notes_tab(), "Notes")
        tabs.addTab(self._build_chat_tab(), "AI Chat")

        self.setCentralWidget(tabs)
        self.statusBar().showMessage("Ready")

    def _build_audio_tab(self) -> QWidget:
        widget = QWidget()
        main_layout = QVBoxLayout(widget)

        upload_group = QGroupBox("Upload Audio")
        upload_layout = QVBoxLayout(upload_group)

        form_layout = QFormLayout()
        self.audio_title_input = QLineEdit()
        self.audio_title_input.setPlaceholderText("Optional title for this lecture")
        form_layout.addRow("Title", self.audio_title_input)
        upload_layout.addLayout(form_layout)

        audio_row = QHBoxLayout()
        self.select_audio_button = QPushButton("Select Audio")
        self.select_audio_button.clicked.connect(self._select_audio_file)
        self.audio_file_label = QLabel("No audio selected")
        self.audio_file_label.setWordWrap(True)
        audio_row.addWidget(self.select_audio_button)
        audio_row.addWidget(self.audio_file_label, 1)
        upload_layout.addLayout(audio_row)

        doc_row = QHBoxLayout()
        self.select_audio_docs_button = QPushButton("Select Optional Documents")
        self.select_audio_docs_button.clicked.connect(self._select_audio_documents)
        self.audio_docs_hint_label = QLabel("Optional docs uploaded here are processed and linked to this audio.")
        self.audio_docs_hint_label.setWordWrap(True)
        doc_row.addWidget(self.select_audio_docs_button)
        doc_row.addWidget(self.audio_docs_hint_label, 1)
        upload_layout.addLayout(doc_row)

        self.audio_docs_list = QListWidget()
        self.audio_docs_list.setMaximumHeight(90)
        self.audio_docs_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        upload_layout.addWidget(self.audio_docs_list)

        self.start_pipeline_button = QPushButton("Upload + Transcribe")
        self.start_pipeline_button.clicked.connect(self._start_audio_pipeline)
        upload_layout.addWidget(self.start_pipeline_button)

        main_layout.addWidget(upload_group)

        transcript_group = QGroupBox("Stored Transcripts")
        transcript_layout = QVBoxLayout(transcript_group)

        selector_row = QHBoxLayout()
        self.audio_selector_combo = QComboBox()
        self.audio_selector_combo.currentIndexChanged.connect(self._load_selected_transcript)
        self.refresh_audio_button = QPushButton("Refresh")
        self.refresh_audio_button.clicked.connect(self._refresh_all)
        selector_row.addWidget(QLabel("Select audio"))
        selector_row.addWidget(self.audio_selector_combo, 1)
        selector_row.addWidget(self.refresh_audio_button)
        transcript_layout.addLayout(selector_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        raw_wrapper = QWidget()
        raw_layout = QVBoxLayout(raw_wrapper)
        raw_layout.addWidget(QLabel("Raw transcript"))
        self.raw_transcript_text = QPlainTextEdit()
        self.raw_transcript_text.setReadOnly(True)
        raw_layout.addWidget(self.raw_transcript_text)

        corrected_wrapper = QWidget()
        corrected_layout = QVBoxLayout(corrected_wrapper)
        corrected_layout.addWidget(QLabel("Corrected transcript"))
        self.corrected_transcript_text = QPlainTextEdit()
        self.corrected_transcript_text.setReadOnly(True)
        corrected_layout.addWidget(self.corrected_transcript_text)

        splitter.addWidget(raw_wrapper)
        splitter.addWidget(corrected_wrapper)
        splitter.setSizes([1, 1])
        transcript_layout.addWidget(splitter)

        main_layout.addWidget(transcript_group, 1)

        return widget

    def _build_documents_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        controls_group = QGroupBox("Upload Documents")
        controls_layout = QVBoxLayout(controls_group)

        link_row = QHBoxLayout()
        self.document_audio_link_combo = QComboBox()
        link_row.addWidget(QLabel("Link to audio (optional)"))
        link_row.addWidget(self.document_audio_link_combo, 1)
        controls_layout.addLayout(link_row)

        button_row = QHBoxLayout()
        self.select_documents_button = QPushButton("Select Documents")
        self.select_documents_button.clicked.connect(self._select_documents_for_upload)
        self.upload_documents_button = QPushButton("Upload Selected")
        self.upload_documents_button.clicked.connect(self._upload_selected_documents)
        button_row.addWidget(self.select_documents_button)
        button_row.addWidget(self.upload_documents_button)
        controls_layout.addLayout(button_row)

        self.selected_documents_list = QListWidget()
        self.selected_documents_list.setMaximumHeight(90)
        self.selected_documents_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        controls_layout.addWidget(self.selected_documents_list)

        layout.addWidget(controls_group)

        table_group = QGroupBox("Stored Documents")
        table_layout = QVBoxLayout(table_group)
        self.documents_table = QTableWidget(0, 4)
        self.documents_table.setHorizontalHeaderLabels(["ID", "Filename", "Linked Audio", "Created"])
        self.documents_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.documents_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.documents_table.itemSelectionChanged.connect(self._show_selected_document_text)
        self.documents_table.verticalHeader().setVisible(False)
        self.documents_table.horizontalHeader().setStretchLastSection(True)
        table_layout.addWidget(self.documents_table)

        table_layout.addWidget(QLabel("Extracted document text"))
        self.document_text_preview = QPlainTextEdit()
        self.document_text_preview.setReadOnly(True)
        table_layout.addWidget(self.document_text_preview)

        layout.addWidget(table_group, 1)
        return widget

    def _build_notes_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        controls = QHBoxLayout()
        self.notes_audio_combo = QComboBox()
        self.notes_mode_combo = QComboBox()
        self.notes_mode_combo.addItem("Exact teacher wording", NOTE_MODE_EXACT)
        self.notes_mode_combo.addItem("Reformulated version", NOTE_MODE_REFORMULATED)
        self.notes_mode_combo.currentIndexChanged.connect(self._load_latest_note)

        self.generate_notes_button = QPushButton("Generate Notes")
        self.generate_notes_button.clicked.connect(self._generate_notes)
        self.load_latest_note_button = QPushButton("Load Latest")
        self.load_latest_note_button.clicked.connect(self._load_latest_note)

        controls.addWidget(QLabel("Audio"))
        controls.addWidget(self.notes_audio_combo, 1)
        controls.addWidget(QLabel("Mode"))
        controls.addWidget(self.notes_mode_combo)
        controls.addWidget(self.generate_notes_button)
        controls.addWidget(self.load_latest_note_button)

        layout.addLayout(controls)

        self.notes_output = QPlainTextEdit()
        self.notes_output.setReadOnly(True)
        layout.addWidget(self.notes_output, 1)

        return widget

    def _build_chat_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        widget.setStyleSheet("""
            QWidget#ChatTab { background-color: transparent; }
            QComboBox { padding: 6px; border: 1px solid #444; border-radius: 6px; background-color: #2d2d2d; color: #fff; }
            QScrollArea { border: none; background-color: transparent; }
            QWidget#ChatContainer { background-color: transparent; }
            QPlainTextEdit#ChatInput { border: 1px solid #444; border-radius: 15px; padding: 10px 15px; font-size: 14px; background-color: #2d2d2d; color: #fff; }
            QPushButton#SendButton { background-color: #1a73e8; color: white; border: none; border-radius: 15px; padding: 10px 20px; font-size: 14px; font-weight: bold; }
            QPushButton#SendButton:hover { background-color: #1557b0; }
            QPushButton#SendButton:disabled { background-color: #444; color: #888; }
            QPushButton#ClearButton { background-color: #2d2d2d; color: #ccc; border: 1px solid #444; border-radius: 12px; padding: 6px 12px; font-size: 12px; }
            QPushButton#ClearButton:hover { background-color: #3d3d3d; }
        """)
        widget.setObjectName("ChatTab")

        filter_row = QHBoxLayout()
        self.chat_audio_combo = QComboBox()
        filter_label = QLabel("Chat scope:")
        filter_label.setStyleSheet("font-weight: bold; color: #ccc; font-size: 13px;")
        filter_row.addWidget(filter_label)
        filter_row.addWidget(self.chat_audio_combo, 1)

        self.clear_chat_button = QPushButton("Clear Chat")
        self.clear_chat_button.setObjectName("ClearButton")
        self.clear_chat_button.clicked.connect(self._clear_chat)
        filter_row.addWidget(self.clear_chat_button)
        layout.addLayout(filter_row)

        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_container = QWidget()
        self.chat_container.setObjectName("ChatContainer")
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.addStretch()
        self.chat_layout.setSpacing(15)
        self.chat_scroll.setWidget(self.chat_container)
        layout.addWidget(self.chat_scroll, 1)

        input_layout = QHBoxLayout()
        input_layout.setSpacing(10)
        
        self.chat_input = QPlainTextEdit()
        self.chat_input.setObjectName("ChatInput")
        self.chat_input.setPlaceholderText("Ask a question about the audios or documents...")
        self.chat_input.setMaximumHeight(70)
        input_layout.addWidget(self.chat_input, 1)

        self.send_chat_button = QPushButton("Send")
        self.send_chat_button.setObjectName("SendButton")
        self.send_chat_button.clicked.connect(self._send_chat_message)
        self.send_chat_button.setCursor(Qt.CursorShape.PointingHandCursor)
        input_layout.addWidget(self.send_chat_button)
        input_layout.setAlignment(self.send_chat_button, Qt.AlignmentFlag.AlignBottom)
        
        layout.addLayout(input_layout)

        self.chat_sources_label = QLabel("")
        self.chat_sources_label.setWordWrap(True)
        self.chat_sources_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.chat_sources_label)

        return widget

    def _add_chat_bubble(self, text: str, is_user: bool) -> None:
        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        
        layout = QHBoxLayout()
        if is_user:
            bubble.setStyleSheet("""
                background-color: #1a73e8; color: white; padding: 12px 18px;
                border-radius: 18px; border-bottom-right-radius: 4px; font-size: 14px;
            """)
            layout.addStretch()
            layout.addWidget(bubble)
        else:
            bubble.setStyleSheet("""
                background-color: #2d2d2d; color: #e0e0e0; padding: 12px 18px;
                border-radius: 18px; border-bottom-left-radius: 4px; font-size: 14px;
            """)
            layout.addWidget(bubble)
            layout.addStretch()
            
        self.chat_layout.insertLayout(self.chat_layout.count() - 1, layout)
        QTimer.singleShot(100, lambda: self.chat_scroll.verticalScrollBar().setValue(self.chat_scroll.verticalScrollBar().maximum()))

    def _run_async(
        self,
        callback: Any,
        on_success: Any,
        on_error: Any | None = None,
    ) -> None:
        thread = QThread(self)
        worker = FunctionWorker(callback)
        worker.moveToThread(thread)

        def handle_success(result: object) -> None:
            on_success(result)

        def handle_error(message: str) -> None:
            if on_error is not None:
                on_error(message)
            else:
                self._show_error(message)

        def cleanup() -> None:
            if (thread, worker) in self._active_workers:
                self._active_workers.remove((thread, worker))
            worker.deleteLater()
            thread.quit()

        worker.finished.connect(handle_success)
        worker.failed.connect(handle_error)
        worker.finished.connect(cleanup)
        worker.failed.connect(cleanup)
        thread.finished.connect(thread.deleteLater)
        thread.started.connect(worker.run)

        self._active_workers.append((thread, worker))
        thread.start()

    def _select_audio_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select audio file",
            "",
            "Audio Files (*.mp3 *.wav *.m4a *.ogg *.flac *.aac);;All Files (*)",
        )
        if not file_path:
            return

        self._selected_audio_path = file_path
        self.audio_file_label.setText(file_path)

    def _select_audio_documents(self) -> None:
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select documents",
            "",
            "Documents (*.pdf *.txt *.docx *.md);;All Files (*)",
        )
        if not file_paths:
            return

        self._selected_audio_documents = file_paths
        self._set_list_items(self.audio_docs_list, file_paths)

    def _start_audio_pipeline(self) -> None:
        if not self._selected_audio_path:
            QMessageBox.warning(self, "Missing audio", "Select an audio file first.")
            return

        audio_path = self._selected_audio_path
        title = self.audio_title_input.text().strip()
        optional_documents = list(self._selected_audio_documents)

        self.start_pipeline_button.setEnabled(False)
        self.statusBar().showMessage("Processing audio and transcription...")

        def task() -> dict[str, int]:
            audio_id = self.transcription_service.process_audio(audio_path, title)
            document_count = 0
            for path in optional_documents:
                self.document_service.store_document(path, audio_id=audio_id)
                document_count += 1
            return {"audio_id": audio_id, "document_count": document_count}

        def on_success(result: dict[str, int]) -> None:
            self.start_pipeline_button.setEnabled(True)
            self._selected_audio_path = None
            self._selected_audio_documents = []
            self.audio_file_label.setText("No audio selected")
            self.audio_title_input.clear()
            self._set_list_items(self.audio_docs_list, [])
            self._refresh_all()
            self.statusBar().showMessage("Audio processed successfully.")
            QMessageBox.information(
                self,
                "Pipeline complete",
                (
                    f"Audio processed and stored (ID {result['audio_id']}). "
                    f"Linked documents processed: {result['document_count']}."
                ),
            )

        def on_error(message: str) -> None:
            self.start_pipeline_button.setEnabled(True)
            self._show_error(message)

        self._run_async(task, on_success, on_error)

    def _select_documents_for_upload(self) -> None:
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select documents",
            "",
            "Documents (*.pdf *.txt *.docx *.md);;All Files (*)",
        )
        if not file_paths:
            return

        self._selected_document_paths = file_paths
        self._set_list_items(self.selected_documents_list, file_paths)

    def _upload_selected_documents(self) -> None:
        if not self._selected_document_paths:
            QMessageBox.warning(self, "Missing documents", "Select one or more documents first.")
            return

        selected_paths = list(self._selected_document_paths)
        audio_id = self._combo_audio_id(self.document_audio_link_combo)

        self.upload_documents_button.setEnabled(False)
        self.statusBar().showMessage("Uploading documents...")

        def task() -> int:
            count = 0
            for path in selected_paths:
                self.document_service.store_document(path, audio_id=audio_id)
                count += 1
            return count

        def on_success(count: int) -> None:
            self.upload_documents_button.setEnabled(True)
            self._selected_document_paths = []
            self._set_list_items(self.selected_documents_list, [])
            self._refresh_all()
            self.statusBar().showMessage("Documents uploaded.")
            QMessageBox.information(self, "Documents uploaded", f"Stored {count} document(s).")

        def on_error(message: str) -> None:
            self.upload_documents_button.setEnabled(True)
            self._show_error(message)

        self._run_async(task, on_success, on_error)

    def _load_selected_transcript(self) -> None:
        audio_id = self._combo_audio_id(self.audio_selector_combo)
        if audio_id is None:
            self.raw_transcript_text.clear()
            self.corrected_transcript_text.clear()
            return

        transcript = self.database.get_transcript_by_audio(audio_id)
        if transcript is None:
            self.raw_transcript_text.setPlainText("No transcript available yet for this audio.")
            self.corrected_transcript_text.setPlainText("No corrected transcript available yet.")
            return

        self.raw_transcript_text.setPlainText(str(transcript.get("raw_text", "")))
        self.corrected_transcript_text.setPlainText(str(transcript.get("corrected_text", "")))

    def _refresh_documents_table(self) -> None:
        documents = self.database.list_documents()
        self.documents_table.setRowCount(len(documents))
        self._documents_cache = {}

        for row_index, document in enumerate(documents):
            document_id = int(document["id"])
            self._documents_cache[document_id] = document

            linked_audio = document.get("audio_title") or "-"

            self.documents_table.setItem(row_index, 0, QTableWidgetItem(str(document_id)))
            self.documents_table.setItem(row_index, 1, QTableWidgetItem(str(document.get("original_filename", ""))))
            self.documents_table.setItem(row_index, 2, QTableWidgetItem(str(linked_audio)))
            self.documents_table.setItem(row_index, 3, QTableWidgetItem(str(document.get("created_at", ""))))

        if documents:
            self.documents_table.selectRow(0)
        else:
            self.document_text_preview.clear()

    def _show_selected_document_text(self) -> None:
        selected_rows = self.documents_table.selectionModel().selectedRows()
        if not selected_rows:
            self.document_text_preview.clear()
            return

        row_index = selected_rows[0].row()
        id_item = self.documents_table.item(row_index, 0)
        if id_item is None:
            self.document_text_preview.clear()
            return

        try:
            document_id = int(id_item.text())
        except ValueError:
            self.document_text_preview.clear()
            return

        document = self._documents_cache.get(document_id)
        if document is None:
            self.document_text_preview.clear()
            return

        self.document_text_preview.setPlainText(str(document.get("extracted_text", "")))

    def _generate_notes(self) -> None:
        audio_id = self._combo_audio_id(self.notes_audio_combo)
        if audio_id is None:
            QMessageBox.warning(self, "Missing audio", "Select an audio item first.")
            return

        mode = str(self.notes_mode_combo.currentData())
        self.generate_notes_button.setEnabled(False)
        self.statusBar().showMessage("Generating notes...")

        def task() -> str:
            return self.notes_service.generate_notes(audio_id=audio_id, mode=mode)

        def on_success(notes: str) -> None:
            self.generate_notes_button.setEnabled(True)
            self.notes_output.setPlainText(notes)
            self.statusBar().showMessage("Notes generated.")

        def on_error(message: str) -> None:
            self.generate_notes_button.setEnabled(True)
            self._show_error(message)

        self._run_async(task, on_success, on_error)

    def _load_latest_note(self) -> None:
        audio_id = self._combo_audio_id(self.notes_audio_combo)
        if audio_id is None:
            self.notes_output.clear()
            return

        mode = str(self.notes_mode_combo.currentData())
        note = self.database.get_latest_note(audio_id=audio_id, mode=mode)
        if note is None:
            self.notes_output.setPlainText("No notes generated yet for this audio and mode.")
            return

        self.notes_output.setPlainText(str(note.get("content", "")))

    def _send_chat_message(self) -> None:
        question = self.chat_input.toPlainText().strip()
        if not question:
            return

        audio_id = self._combo_audio_id(self.chat_audio_combo)
        self._add_chat_bubble(question, is_user=True)
        self.chat_input.clear()

        self.send_chat_button.setEnabled(False)
        self.statusBar().showMessage("Generating AI response...")

        def task() -> dict[str, object]:
            return self.rag_service.answer_question(question=question, audio_id=audio_id)

        def on_success(result: dict[str, object]) -> None:
            self.send_chat_button.setEnabled(True)
            answer = str(result.get("answer", ""))
            sources = result.get("sources", [])
            source_lines = " | ".join(f"{item}" for item in sources)

            self._add_chat_bubble(answer, is_user=False)
            if source_lines:
                self.chat_sources_label.setText(f"Sources: {source_lines}")
            self.statusBar().showMessage("AI response ready.")

        def on_error(message: str) -> None:
            self.send_chat_button.setEnabled(True)
            self._add_chat_bubble(f"Error - {message}", is_user=False)
            self._show_error(message)

        self._run_async(task, on_success, on_error)

    def _clear_chat(self) -> None:
        # Remove all widgets from the chat layout except the stretch
        while self.chat_layout.count() > 1:
            item = self.chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # remove widgets within the layout
                sub_layout = item.layout()
                while sub_layout.count():
                    sub_item = sub_layout.takeAt(0)
                    if sub_item.widget():
                        sub_item.widget().deleteLater()
                sub_layout.deleteLater()
        
        self.chat_sources_label.clear()

    def _refresh_audio_combos(self) -> None:
        audios = self.database.list_audios()

        current_audio_id = self._combo_audio_id(self.audio_selector_combo)
        current_note_audio_id = self._combo_audio_id(self.notes_audio_combo)
        current_doc_audio_id = self._combo_audio_id(self.document_audio_link_combo)
        current_chat_audio_id = self._combo_audio_id(self.chat_audio_combo)

        self.audio_selector_combo.blockSignals(True)
        self.notes_audio_combo.blockSignals(True)
        self.document_audio_link_combo.blockSignals(True)
        self.chat_audio_combo.blockSignals(True)

        self.audio_selector_combo.clear()
        self.notes_audio_combo.clear()
        self.document_audio_link_combo.clear()
        self.chat_audio_combo.clear()

        self.document_audio_link_combo.addItem("No linked audio", None)
        self.chat_audio_combo.addItem("All sessions", None)

        for audio in audios:
            audio_id = int(audio["id"])
            title = str(audio.get("title", f"Audio {audio_id}"))
            item_label = f"{audio_id} - {title}"
            self.audio_selector_combo.addItem(item_label, audio_id)
            self.notes_audio_combo.addItem(item_label, audio_id)
            self.document_audio_link_combo.addItem(item_label, audio_id)
            self.chat_audio_combo.addItem(item_label, audio_id)

        self.audio_selector_combo.blockSignals(False)
        self.notes_audio_combo.blockSignals(False)
        self.document_audio_link_combo.blockSignals(False)
        self.chat_audio_combo.blockSignals(False)

        self._restore_combo_selection(self.audio_selector_combo, current_audio_id)
        self._restore_combo_selection(self.notes_audio_combo, current_note_audio_id)
        self._restore_combo_selection(self.document_audio_link_combo, current_doc_audio_id)
        self._restore_combo_selection(self.chat_audio_combo, current_chat_audio_id)

    def _refresh_all(self) -> None:
        self._refresh_audio_combos()
        self._load_selected_transcript()
        self._refresh_documents_table()
        self._load_latest_note()

    def _restore_combo_selection(self, combo: QComboBox, value: int | None) -> None:
        if combo.count() == 0:
            return
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)
        else:
            combo.setCurrentIndex(0)

    def _combo_audio_id(self, combo: QComboBox) -> int | None:
        data = combo.currentData()
        if data is None:
            return None
        try:
            return int(data)
        except (TypeError, ValueError):
            return None

    def _set_list_items(self, list_widget: QListWidget, values: list[str]) -> None:
        list_widget.clear()
        for value in values:
            list_widget.addItem(value)

    def _show_error(self, message: str) -> None:
        self.statusBar().showMessage("Operation failed.")
        QMessageBox.critical(self, "Error", message)

    def closeEvent(self, event: QCloseEvent) -> None:
        for thread, _ in list(self._active_workers):
            thread.quit()
            thread.wait(2000)
        super().closeEvent(event)
