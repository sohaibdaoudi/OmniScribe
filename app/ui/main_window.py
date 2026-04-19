from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt, QThread, QTimer, QSize
from PyQt6.QtGui import QCloseEvent, QColor, QPalette, QFont, QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
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
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QProgressBar,
    QTextEdit,
    QHeaderView,
)

from app.database import Database
from app.services.document_service import DocumentService
from app.services.notes_service import NOTE_MODE_EXACT, NOTE_MODE_REFORMULATED, NotesService
from app.services.rag_service import RagService
from app.services.transcription_service import TranscriptionService
from app.ui.workers import FunctionWorker


# ── Palette ────────────────────────────────────────────────────────────────────
BG0   = "#0d0e11"   # deepest
BG1   = "#14161b"   # sidebar
BG2   = "#1c1f27"   # cards / panels
BG3   = "#242832"   # inputs / rows
BORDER     = "rgba(255,255,255,0.07)"
BORDER2    = "rgba(255,255,255,0.13)"
TEXT       = "#e8eaf0"
TEXT2      = "#8b8fa8"
TEXT3      = "#555a70"
ACCENT     = "#6b6ef9"
ACCENT2    = "#8b8dfa"
ACCENT_S   = "rgba(107,110,249,0.12)"
ACCENT_G   = "rgba(107,110,249,0.25)"
GREEN      = "#34d399"
GREEN_S    = "rgba(52,211,153,0.10)"
AMBER      = "#fbbf24"
AMBER_S    = "rgba(251,191,36,0.10)"
RED        = "#f87171"


def css_border(color: str = BORDER) -> str:
    return f"border: 1px solid {color};"


# ── Reusable styled widgets ────────────────────────────────────────────────────

class StyledButton(QPushButton):
    """Primary (filled) or ghost (outlined) push button."""

    def __init__(self, text: str, primary: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        radius = "10px"
        if primary:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: {ACCENT};
                    color: white;
                    border: none;
                    border-radius: {radius};
                    padding: 8px 20px;
                    font-size: 13px;
                    font-weight: 600;
                }}
                QPushButton:hover {{ background: {ACCENT2}; }}
                QPushButton:disabled {{ background: #3a3d5c; color: {TEXT3}; }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {TEXT2};
                    border: 1px solid {BORDER2};
                    border-radius: {radius};
                    padding: 8px 16px;
                    font-size: 13px;
                }}
                QPushButton:hover {{ background: {BG2}; color: {TEXT}; }}
                QPushButton:disabled {{ color: {TEXT3}; }}
            """)


class StyledInput(QLineEdit):
    def __init__(self, placeholder: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setStyleSheet(f"""
            QLineEdit {{
                background: {BG2};
                color: {TEXT};
                border: 1px solid {BORDER2};
                border-radius: 10px;
                padding: 9px 14px;
                font-size: 13px;
            }}
            QLineEdit:focus {{ border: 1px solid {ACCENT}; }}
            QLineEdit::placeholder {{ color: {TEXT3}; }}
        """)


class StyledCombo(QComboBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"""
            QComboBox {{
                background: {BG2};
                color: {TEXT};
                border: 1px solid {BORDER2};
                border-radius: 10px;
                padding: 8px 14px;
                font-size: 13px;
                min-width: 160px;
            }}
            QComboBox:focus {{ border: 1px solid {ACCENT}; }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
            QComboBox QAbstractItemView {{
                background: {BG2};
                color: {TEXT};
                border: 1px solid {BORDER2};
                selection-background-color: {ACCENT_S};
                selection-color: {ACCENT2};
            }}
        """)


class MonoLabel(QLabel):
    """Small monospace metadata label."""

    def __init__(self, text: str = "", color: str = TEXT3, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setStyleSheet(f"color: {color}; font-family: 'Courier New', monospace; font-size: 11px;")


class SectionLabel(QLabel):
    """Uppercase monospace section header."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text.upper(), parent)
        self.setStyleSheet(
            f"color: {TEXT3}; font-family: 'Courier New', monospace; "
            f"font-size: 10px; letter-spacing: 1px;"
        )


class Card(QFrame):
    """Dark rounded card container."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background: {BG1};
                border: 1px solid {BORDER};
                border-radius: 14px;
            }}
        """)


class PanelFrame(QFrame):
    """Panel with header stripe and body."""

    def __init__(self, title: str, tag: str = "", tag_live: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame#panel {{
                background: {BG1};
                border: 1px solid {BORDER};
                border-radius: 14px;
            }}
        """)
        self.setObjectName("panel")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # header
        header = QWidget()
        header.setStyleSheet(f"background: transparent; border-bottom: 1px solid {BORDER};")
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(16, 10, 16, 10)

        title_lbl = MonoLabel(title, TEXT2)
        hlay.addWidget(title_lbl)
        hlay.addStretch()

        if tag:
            tag_bg   = GREEN_S if tag_live else BG3
            tag_col  = GREEN   if tag_live else TEXT3
            tag_lbl  = MonoLabel(tag, tag_col)
            tag_lbl.setStyleSheet(
                f"color: {tag_col}; background: {tag_bg}; "
                f"border-radius: 99px; padding: 2px 9px; font-size: 10px;"
                f"font-family: 'Courier New', monospace;"
            )
            hlay.addWidget(tag_lbl)

        outer.addWidget(header)

        # body
        self.body = QWidget()
        self.body.setStyleSheet("background: transparent; border: none;")
        self._body_layout = QVBoxLayout(self.body)
        self._body_layout.setContentsMargins(16, 14, 16, 14)
        outer.addWidget(self.body, 1)

    def body_layout(self) -> QVBoxLayout:
        return self._body_layout


class UploadDropZone(QFrame):
    def __init__(self, title: str, subtitle: str, formats: list[str] | None = None, compact: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._normal_style = f"""
            QFrame {{
                background: {BG1};
                border: 1.5px dashed {BORDER2};
                border-radius: 14px;
            }}
        """
        self._hover_style = f"""
            QFrame {{
                background: {ACCENT_S};
                border: 1.5px dashed {ACCENT};
                border-radius: 14px;
            }}
        """
        self.setStyleSheet(self._normal_style)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QVBoxLayout(self)
        if compact:
            lay.setContentsMargins(18, 14, 18, 14)
            lay.setSpacing(6)

            row = QHBoxLayout()
            icon_box = self._make_icon_box(compact=True)
            row.addWidget(icon_box)

            text_col = QVBoxLayout()
            t = QLabel(title)
            t.setStyleSheet(f"color: {TEXT}; font-size: 13px; font-weight: 600; border: none; background: transparent;")
            s = QLabel(subtitle)
            s.setStyleSheet(f"color: {TEXT3}; font-size: 11px; border: none; background: transparent;")
            text_col.addWidget(t)
            text_col.addWidget(s)
            row.addLayout(text_col)
            row.addStretch()
            lay.addLayout(row)
        else:
            lay.setContentsMargins(32, 28, 32, 28)
            lay.setSpacing(0)
            lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

            icon_box = self._make_icon_box()
            icon_box.setFixedSize(52, 52)
            lay.addWidget(icon_box, alignment=Qt.AlignmentFlag.AlignHCenter)
            lay.addSpacing(14)

            t = QLabel(title)
            t.setStyleSheet(f"color: {TEXT}; font-size: 14px; font-weight: 600; border: none; background: transparent;")
            t.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(t)

            s = QLabel(subtitle)
            s.setStyleSheet(f"color: {TEXT3}; font-size: 12px; border: none; background: transparent;")
            s.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(s)

            if formats:
                lay.addSpacing(14)
                fmt_row = QHBoxLayout()
                fmt_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
                fmt_row.setSpacing(6)
                for f in formats:
                    chip = QLabel(f)
                    chip.setStyleSheet(
                        f"color: {TEXT3}; background: {BG3}; "
                        f"border: 1px solid {BORDER}; border-radius: 99px; "
                        f"padding: 3px 9px; font-size: 10px; font-family: 'Courier New', monospace;"
                    )
                    fmt_row.addWidget(chip)
                fmt_widget = QWidget()
                fmt_widget.setStyleSheet("background: transparent; border: none;")
                fmt_widget.setLayout(fmt_row)
                lay.addWidget(fmt_widget)

    def _make_icon_box(self, compact: bool = False) -> QLabel:
        size = 36 if compact else 48
        icon = QLabel("↑")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(size, size)
        icon.setStyleSheet(
            f"color: {ACCENT2}; background: {BG2}; "
            f"border: 1px solid {BORDER2}; border-radius: 12px; "
            f"font-size: {'16px' if compact else '20px'}; font-weight: bold;"
        )
        return icon

    def enterEvent(self, event: Any) -> None:
        self.setStyleSheet(self._hover_style)

    def leaveEvent(self, event: Any) -> None:
        self.setStyleSheet(self._normal_style)


# ── Nav item ──────────────────────────────────────────────────────────────────

class NavItem(QWidget):
    def __init__(self, icon_text: str, label: str, badge: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._active = False

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(10, 8, 10, 8)
        self._layout.setSpacing(10)

        self._icon = QLabel(icon_text)
        self._icon.setFixedSize(18, 18)
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon.setStyleSheet(f"color: {TEXT2}; font-size: 14px; background: transparent; border: none;")

        self._label = QLabel(label)
        self._label.setStyleSheet(f"color: {TEXT2}; font-size: 13px; background: transparent; border: none;")

        self._layout.addWidget(self._icon)
        self._layout.addWidget(self._label, 1)

        if badge:
            self._badge = QLabel(badge)
            self._badge.setStyleSheet(
                f"color: {TEXT3}; background: {BG3}; border-radius: 99px; "
                f"padding: 1px 7px; font-size: 10px; font-family: 'Courier New', monospace;"
            )
            self._layout.addWidget(self._badge)
        else:
            self._badge = None

        self._set_style(False)

    def _set_style(self, active: bool) -> None:
        if active:
            self.setStyleSheet(
                f"QWidget {{ background: {ACCENT_S}; border: 1px solid {ACCENT_G}; border-radius: 10px; }}"
            )
            self._label.setStyleSheet(f"color: {ACCENT2}; font-size: 13px; background: transparent; border: none;")
            self._icon.setStyleSheet(f"color: {ACCENT2}; font-size: 14px; background: transparent; border: none;")
            if self._badge:
                self._badge.setStyleSheet(
                    f"color: {ACCENT2}; background: {ACCENT_G}; border-radius: 99px; "
                    f"padding: 1px 7px; font-size: 10px; font-family: 'Courier New', monospace;"
                )
        else:
            self.setStyleSheet(
                f"QWidget {{ background: transparent; border: 1px solid transparent; border-radius: 10px; }}"
                f"QWidget:hover {{ background: {BG2}; }}"
            )
            self._label.setStyleSheet(f"color: {TEXT2}; font-size: 13px; background: transparent; border: none;")
            self._icon.setStyleSheet(f"color: {TEXT2}; font-size: 14px; background: transparent; border: none;")
            if self._badge:
                self._badge.setStyleSheet(
                    f"color: {TEXT3}; background: {BG3}; border-radius: 99px; "
                    f"padding: 1px 7px; font-size: 10px; font-family: 'Courier New', monospace;"
                )

    def set_active(self, active: bool) -> None:
        self._active = active
        self._set_style(active)

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.parent().parent()._on_nav_click(self)  # type: ignore[attr-defined]


# ── Main Window ───────────────────────────────────────────────────────────────

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
        self._nav_items: list[NavItem] = []

        self.setWindowTitle("OmniScribe")
        self.resize(1280, 820)
        self.setMinimumSize(960, 640)

        # Global app style
        self.setStyleSheet(f"""
            QMainWindow {{ background: {BG0}; }}
            QWidget {{ background: {BG0}; color: {TEXT}; font-family: 'Segoe UI', 'SF Pro Display', sans-serif; }}
            QScrollBar:vertical {{
                background: transparent; width: 6px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {BG3}; border-radius: 3px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar:horizontal {{
                background: transparent; height: 6px; margin: 0;
            }}
            QScrollBar::handle:horizontal {{
                background: {BG3}; border-radius: 3px; min-width: 20px;
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
            QStatusBar {{ background: {BG1}; color: {TEXT3}; font-size: 11px; border-top: 1px solid {BORDER}; }}
        """)

        self._build_ui()
        self._refresh_all()

    # ── Layout ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_sidebar())

        # separator line
        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"background: {BORDER};")
        root_layout.addWidget(sep)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet(f"background: {BG0};")
        self.stack.addWidget(self._build_audio_page())    # 0
        self.stack.addWidget(self._build_documents_page()) # 1
        self.stack.addWidget(self._build_notes_page())    # 2
        self.stack.addWidget(self._build_chat_page())     # 3
        root_layout.addWidget(self.stack, 1)

        self.setCentralWidget(root)
        self.statusBar().showMessage("Ready")

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setFixedWidth(230)
        sidebar.setStyleSheet(f"background: {BG1};")

        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Logo
        logo_widget = QWidget()
        logo_widget.setStyleSheet(f"background: transparent; border-bottom: 1px solid {BORDER};")
        logo_lay = QHBoxLayout(logo_widget)
        logo_lay.setContentsMargins(18, 18, 18, 16)
        logo_lay.setSpacing(10)

        logo_icon = QLabel("▶")
        logo_icon.setFixedSize(32, 32)
        logo_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_icon.setStyleSheet(
            f"background: {ACCENT}; color: white; border-radius: 8px; font-size: 14px; border: none;"
        )
        logo_lay.addWidget(logo_icon)

        logo_text = QWidget()
        logo_text.setStyleSheet("background: transparent; border: none;")
        lt_lay = QVBoxLayout(logo_text)
        lt_lay.setContentsMargins(0, 0, 0, 0)
        lt_lay.setSpacing(1)
        name_lbl = QLabel("OmniScribe")
        name_lbl.setStyleSheet(f"color: {TEXT}; font-size: 15px; font-weight: 700; background: transparent; border: none;")
        tag_lbl = MonoLabel("v0.1 MVP")
        lt_lay.addWidget(name_lbl)
        lt_lay.addWidget(tag_lbl)
        logo_lay.addWidget(logo_text)
        lay.addWidget(logo_widget)

        # Nav
        nav_container = QWidget()
        nav_container.setStyleSheet("background: transparent;")
        nav_lay = QVBoxLayout(nav_container)
        nav_lay.setContentsMargins(10, 12, 10, 0)
        nav_lay.setSpacing(2)

        section_lbl = SectionLabel("Workspace")
        section_lbl.setContentsMargins(8, 6, 0, 4)
        nav_lay.addWidget(section_lbl)

        items = [
            ("♪", "Audio", "3"),
            ("📄", "Documents", "7"),
            ("✏", "Notes", ""),
            ("💬", "AI Chat", ""),
        ]
        for icon, label, badge in items:
            item = NavItem(icon, label, badge)
            nav_lay.addWidget(item)
            self._nav_items.append(item)

        nav_lay.addStretch()
        lay.addWidget(nav_container, 1)

        # Footer status
        footer = QWidget()
        footer.setStyleSheet(f"background: transparent; border-top: 1px solid {BORDER};")
        f_lay = QVBoxLayout(footer)
        f_lay.setContentsMargins(10, 12, 10, 12)

        status_pill = QWidget()
        status_pill.setStyleSheet(
            f"background: {GREEN_S}; border-radius: 10px;"
        )
        sp_lay = QHBoxLayout(status_pill)
        sp_lay.setContentsMargins(10, 8, 10, 8)
        sp_lay.setSpacing(8)

        dot = QLabel("●")
        dot.setStyleSheet(f"color: {GREEN}; font-size: 10px; background: transparent; border: none;")
        status_text = MonoLabel("whisper-large ready", GREEN)
        sp_lay.addWidget(dot)
        sp_lay.addWidget(status_text, 1)
        f_lay.addWidget(status_pill)
        lay.addWidget(footer)

        # Activate first
        self._nav_items[0].set_active(True)
        return sidebar

    def _on_nav_click(self, item: NavItem) -> None:
        for i, nav in enumerate(self._nav_items):
            nav.set_active(nav is item)
            if nav is item:
                self.stack.setCurrentIndex(i)

    # ── Topbar helper ────────────────────────────────────────────────────────

    def _make_topbar(self, title: str, subtitle: str, actions: list[QWidget]) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(60)
        bar.setStyleSheet(f"background: {BG0}; border-bottom: 1px solid {BORDER};")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(24, 0, 24, 0)

        text_col = QWidget()
        text_col.setStyleSheet("background: transparent; border: none;")
        tc_lay = QVBoxLayout(text_col)
        tc_lay.setContentsMargins(0, 0, 0, 0)
        tc_lay.setSpacing(2)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"color: {TEXT}; font-size: 15px; font-weight: 700; background: transparent; border: none;")
        sub_lbl = MonoLabel(subtitle)
        tc_lay.addWidget(title_lbl)
        tc_lay.addWidget(sub_lbl)
        lay.addWidget(text_col)
        lay.addStretch()

        for w in actions:
            lay.addWidget(w)

        return bar

    # ── Sub-tab bar ──────────────────────────────────────────────────────────

    def _make_subtab_bar(self, labels: list[str], stack: QStackedWidget) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet(f"background: {BG0}; border-bottom: 1px solid {BORDER};")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(24, 0, 0, 0)
        lay.setSpacing(0)

        buttons: list[QPushButton] = []

        def activate(idx: int) -> None:
            stack.setCurrentIndex(idx)
            for i, b in enumerate(buttons):
                if i == idx:
                    b.setStyleSheet(
                        f"color: {ACCENT2}; background: transparent; border: none; "
                        f"border-bottom: 2px solid {ACCENT}; padding: 12px 16px; font-size: 13px;"
                    )
                else:
                    b.setStyleSheet(
                        f"color: {TEXT3}; background: transparent; border: none; "
                        f"border-bottom: 2px solid transparent; padding: 12px 16px; font-size: 13px;"
                    )

        for i, lbl in enumerate(labels):
            btn = QPushButton(lbl)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            idx = i
            btn.clicked.connect(lambda _, x=idx: activate(x))
            lay.addWidget(btn)
            buttons.append(btn)

        lay.addStretch()
        activate(0)
        return bar

    # ── AUDIO PAGE ───────────────────────────────────────────────────────────

    def _build_audio_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet(f"background: {BG0};")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Topbar
        refresh_btn = StyledButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_all)
        upload_btn = StyledButton("+ Upload Audio", primary=True)
        upload_btn.clicked.connect(self._start_audio_pipeline)
        self.start_pipeline_button = upload_btn
        lay.addWidget(self._make_topbar("Audio & Transcripts", "upload → transcribe → review", [refresh_btn, upload_btn]))

        # Sub-tabs
        sub_stack = QStackedWidget()
        sub_stack.setStyleSheet(f"background: {BG0};")
        sub_stack.addWidget(self._build_audio_upload_sub())
        sub_stack.addWidget(self._build_audio_transcripts_sub())
        lay.addWidget(self._make_subtab_bar(["Upload", "Transcripts"], sub_stack))
        lay.addWidget(sub_stack, 1)
        return page

    def _build_audio_upload_sub(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")

        inner = QWidget()
        inner.setStyleSheet(f"background: {BG0};")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(16)

        # Drop zone
        self.audio_drop_zone = UploadDropZone(
            "Drop your audio file here",
            "or click to browse files",
            formats=["mp3", "wav", "m4a", "flac", "ogg", "aac"],
        )
        self.audio_drop_zone.mousePressEvent = lambda e: self._select_audio_file()
        lay.addWidget(self.audio_drop_zone)

        self.audio_file_label = MonoLabel("No file selected", TEXT3)
        lay.addWidget(self.audio_file_label)

        # Title field
        title_section = QWidget()
        title_section.setStyleSheet("background: transparent;")
        ts_lay = QVBoxLayout(title_section)
        ts_lay.setContentsMargins(0, 0, 0, 0)
        ts_lay.setSpacing(6)
        ts_lay.addWidget(SectionLabel("Lecture Title"))
        self.audio_title_input = StyledInput("e.g. Introduction to Machine Learning — Lecture 3")
        ts_lay.addWidget(self.audio_title_input)
        lay.addWidget(title_section)

        # Docs section
        docs_section = QWidget()
        docs_section.setStyleSheet("background: transparent;")
        ds_lay = QVBoxLayout(docs_section)
        ds_lay.setContentsMargins(0, 0, 0, 0)
        ds_lay.setSpacing(6)
        ds_lay.addWidget(SectionLabel("Attach Supporting Documents (Optional)"))

        docs_drop = UploadDropZone(
            "Attach slides, PDFs, notes",
            "Will be linked to this audio session",
            compact=True,
        )

        browse_btn = StyledButton("Browse")
        browse_btn.clicked.connect(self._select_audio_documents)
        browse_btn.setParent(docs_drop)

        # rebuild compact layout to include browse button
        docs_drop_lay = docs_drop.layout()
        if isinstance(docs_drop_lay, QHBoxLayout):
            docs_drop_lay.addWidget(browse_btn)

        ds_lay.addWidget(docs_drop)

        self.audio_docs_list = QListWidget()
        self.audio_docs_list.setMaximumHeight(70)
        self.audio_docs_list.setStyleSheet(
            f"background: transparent; border: none; color: {TEXT3}; font-size: 12px;"
        )
        ds_lay.addWidget(self.audio_docs_list)
        lay.addWidget(docs_section)

        # Progress bar (hidden by default)
        self.progress_widget = QWidget()
        self.progress_widget.setStyleSheet(
            f"background: {ACCENT_S}; border: 1px solid {ACCENT_G}; border-radius: 10px;"
        )
        pw_lay = QHBoxLayout(self.progress_widget)
        pw_lay.setContentsMargins(14, 10, 14, 10)
        self.progress_label = MonoLabel("Transcribing...", ACCENT2)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # indeterminate
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(
            f"QProgressBar {{ background: {BG3}; border-radius: 2px; border: none; }}"
            f"QProgressBar::chunk {{ background: {ACCENT}; border-radius: 2px; }}"
        )
        pw_lay.addWidget(self.progress_label, 1)
        pw_lay.addWidget(self.progress_bar, 2)
        self.progress_widget.hide()
        lay.addWidget(self.progress_widget)

        lay.addStretch()
        scroll.setWidget(inner)
        return scroll

    def _build_audio_transcripts_sub(self) -> QWidget:
        widget = QWidget()
        widget.setStyleSheet(f"background: {BG0};")
        lay = QVBoxLayout(widget)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(14)

        # Selector
        selector_row = QHBoxLayout()
        selector_row.setSpacing(10)
        lbl = QLabel("Session")
        lbl.setStyleSheet(f"color: {TEXT2}; font-size: 13px;")
        self.audio_selector_combo = StyledCombo()
        self.audio_selector_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.audio_selector_combo.currentIndexChanged.connect(self._load_selected_transcript)
        selector_row.addWidget(lbl)
        selector_row.addWidget(self.audio_selector_combo, 1)
        lay.addLayout(selector_row)

        # Two panels
        panels_row = QHBoxLayout()
        panels_row.setSpacing(14)

        raw_panel = PanelFrame("raw transcript", "whisper-large-v3")
        self.raw_transcript_text = QPlainTextEdit()
        self.raw_transcript_text.setReadOnly(True)
        self.raw_transcript_text.setStyleSheet(
            f"background: transparent; border: none; color: {TEXT2}; "
            f"font-size: 13px; line-height: 1.7;"
        )
        raw_panel.body_layout().addWidget(self.raw_transcript_text)
        panels_row.addWidget(raw_panel)

        corrected_panel = PanelFrame("corrected transcript", "corrected", tag_live=True)
        self.corrected_transcript_text = QPlainTextEdit()
        self.corrected_transcript_text.setReadOnly(True)
        self.corrected_transcript_text.setStyleSheet(
            f"background: transparent; border: none; color: {TEXT2}; "
            f"font-size: 13px; line-height: 1.7;"
        )
        corrected_panel.body_layout().addWidget(self.corrected_transcript_text)
        panels_row.addWidget(corrected_panel)

        lay.addLayout(panels_row, 1)
        return widget

    # ── DOCUMENTS PAGE ────────────────────────────────────────────────────────

    def _build_documents_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet(f"background: {BG0};")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.document_audio_link_combo = StyledCombo()
        self.select_documents_button = StyledButton("Select Docs")
        self.select_documents_button.clicked.connect(self._select_documents_for_upload)
        upload_btn = StyledButton("Upload Selected", primary=True)
        upload_btn.clicked.connect(self._upload_selected_documents)
        self.upload_documents_button = upload_btn

        lay.addWidget(self._make_topbar(
            "Documents",
            "select → link → upload",
            [self.document_audio_link_combo, self.select_documents_button, upload_btn],
        ))

        content = QWidget()
        content.setStyleSheet(f"background: {BG0};")
        c_lay = QVBoxLayout(content)
        c_lay.setContentsMargins(24, 18, 24, 18)
        c_lay.setSpacing(14)

        self.selected_documents_list = QListWidget()
        self.selected_documents_list.setMaximumHeight(60)
        self.selected_documents_list.setStyleSheet(
            f"background: transparent; border: 1px solid {BORDER}; "
            f"border-radius: 10px; color: {TEXT3}; font-size: 12px; padding: 4px;"
        )
        c_lay.addWidget(self.selected_documents_list)

        # Table panel
        table_panel = PanelFrame("stored documents")
        self.documents_table = QTableWidget(0, 4)
        self.documents_table.setHorizontalHeaderLabels(["Filename", "Linked Session", "Preview", "Added"])
        self.documents_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.documents_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.documents_table.verticalHeader().setVisible(False)
        self.documents_table.horizontalHeader().setStretchLastSection(True)
        self.documents_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.documents_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.documents_table.setShowGrid(False)
        self.documents_table.setStyleSheet(f"""
            QTableWidget {{
                background: transparent; border: none; color: {TEXT2};
                font-size: 13px; gridline-color: transparent;
            }}
            QTableWidget::item {{ padding: 10px 14px; border-bottom: 1px solid {BORDER}; }}
            QTableWidget::item:selected {{ background: {BG2}; color: {TEXT}; }}
            QHeaderView::section {{
                background: transparent; color: {TEXT3};
                font-size: 10px; font-family: 'Courier New', monospace;
                text-transform: uppercase; letter-spacing: 1px;
                padding: 10px 14px; border: none;
                border-bottom: 1px solid {BORDER};
            }}
        """)
        self.documents_table.itemSelectionChanged.connect(self._show_selected_document_text)
        table_panel.body_layout().addWidget(self.documents_table)
        c_lay.addWidget(table_panel, 1)

        # Preview panel
        preview_panel = PanelFrame("document preview")
        self.document_text_preview = QPlainTextEdit()
        self.document_text_preview.setReadOnly(True)
        self.document_text_preview.setStyleSheet(
            f"background: transparent; border: none; color: {TEXT2}; font-size: 13px; line-height: 1.7;"
        )
        preview_panel.body_layout().addWidget(self.document_text_preview)
        c_lay.addWidget(preview_panel, 1)

        lay.addWidget(content, 1)
        return page

    # ── NOTES PAGE ────────────────────────────────────────────────────────────

    def _build_notes_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet(f"background: {BG0};")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.notes_audio_combo = StyledCombo()
        self.notes_mode_combo = StyledCombo()
        self.notes_mode_combo.addItem("Exact teacher wording", NOTE_MODE_EXACT)
        self.notes_mode_combo.addItem("Reformulated version", NOTE_MODE_REFORMULATED)
        self.notes_mode_combo.currentIndexChanged.connect(self._load_latest_note)

        load_btn = StyledButton("Load Latest")
        load_btn.clicked.connect(self._load_latest_note)
        self.load_latest_note_button = load_btn

        gen_btn = StyledButton("Generate Notes", primary=True)
        gen_btn.clicked.connect(self._generate_notes)
        self.generate_notes_button = gen_btn

        lay.addWidget(self._make_topbar(
            "Generated Notes",
            "AI-structured study notes",
            [self.notes_audio_combo, self.notes_mode_combo, load_btn, gen_btn],
        ))

        content = QWidget()
        content.setStyleSheet(f"background: {BG0};")
        c_lay = QVBoxLayout(content)
        c_lay.setContentsMargins(24, 18, 24, 18)
        c_lay.setSpacing(0)

        notes_panel = PanelFrame("notes", "generated", tag_live=True)
        self.notes_output = QPlainTextEdit()
        self.notes_output.setReadOnly(True)
        self.notes_output.setStyleSheet(
            f"background: transparent; border: none; color: {TEXT2}; "
            f"font-size: 13.5px; line-height: 1.85;"
        )
        notes_panel.body_layout().addWidget(self.notes_output)
        c_lay.addWidget(notes_panel, 1)

        lay.addWidget(content, 1)
        return page

    # ── CHAT PAGE ─────────────────────────────────────────────────────────────

    def _build_chat_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet(f"background: {BG0};")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.chat_audio_combo = StyledCombo()
        self.chat_audio_combo.addItem("All sessions", None)

        clear_btn = StyledButton("Clear chat")
        clear_btn.clicked.connect(self._clear_chat)

        lay.addWidget(self._make_topbar(
            "AI Chat",
            "RAG over your sessions + docs",
            [self.chat_audio_combo, clear_btn],
        ))

        # Chat scroll area
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setStyleSheet("background: transparent; border: none;")

        self.chat_container = QWidget()
        self.chat_container.setStyleSheet(f"background: {BG0};")
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(24, 16, 24, 16)
        self.chat_layout.setSpacing(14)
        self.chat_layout.addStretch()
        self.chat_scroll.setWidget(self.chat_container)
        lay.addWidget(self.chat_scroll, 1)

        # Sources bar
        self.chat_sources_label = MonoLabel("", TEXT3)
        self.chat_sources_label.setWordWrap(True)
        sources_wrap = QWidget()
        sources_wrap.setStyleSheet(f"background: {BG1}; border-top: 1px solid {BORDER};")
        sw_lay = QHBoxLayout(sources_wrap)
        sw_lay.setContentsMargins(24, 8, 24, 8)
        sw_lay.addWidget(MonoLabel("sources:", TEXT3))
        sw_lay.addWidget(self.chat_sources_label, 1)
        lay.addWidget(sources_wrap)

        # Input bar
        input_bar = QWidget()
        input_bar.setStyleSheet(f"background: {BG1}; border-top: 1px solid {BORDER};")
        ib_lay = QHBoxLayout(input_bar)
        ib_lay.setContentsMargins(24, 12, 24, 12)
        ib_lay.setSpacing(10)

        self.chat_input = QPlainTextEdit()
        self.chat_input.setPlaceholderText("Ask about your lectures or documents...")
        self.chat_input.setMaximumHeight(70)
        self.chat_input.setStyleSheet(f"""
            QPlainTextEdit {{
                background: {BG2}; border: 1px solid {BORDER2};
                border-radius: 12px; padding: 9px 14px;
                font-size: 13.5px; color: {TEXT};
            }}
            QPlainTextEdit:focus {{ border: 1px solid {ACCENT}; }}
        """)
        ib_lay.addWidget(self.chat_input, 1)

        self.send_chat_button = QPushButton("➤")
        self.send_chat_button.setFixedSize(40, 40)
        self.send_chat_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_chat_button.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT}; color: white;
                border: none; border-radius: 10px; font-size: 15px;
            }}
            QPushButton:hover {{ background: {ACCENT2}; }}
            QPushButton:disabled {{ background: #3a3d5c; }}
        """)
        self.send_chat_button.clicked.connect(self._send_chat_message)
        ib_lay.addWidget(self.send_chat_button, alignment=Qt.AlignmentFlag.AlignBottom)

        lay.addWidget(input_bar)
        return page

    # ── Chat bubbles ─────────────────────────────────────────────────────────

    def _add_chat_bubble(self, text: str, is_user: bool) -> None:
        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bubble.setMaximumWidth(600)

        if is_user:
            bubble.setStyleSheet(
                f"background: {ACCENT}; color: white; padding: 10px 16px; "
                f"border-radius: 16px; border-bottom-right-radius: 4px; font-size: 13.5px;"
            )
            row = QHBoxLayout()
            row.addStretch()
            row.addWidget(bubble)
        else:
            bubble.setStyleSheet(
                f"background: {BG2}; color: {TEXT}; padding: 10px 16px; "
                f"border: 1px solid {BORDER}; "
                f"border-radius: 16px; border-bottom-left-radius: 4px; font-size: 13.5px;"
            )
            row = QHBoxLayout()
            row.addWidget(bubble)
            row.addStretch()

        self.chat_layout.insertLayout(self.chat_layout.count() - 1, row)
        QTimer.singleShot(
            100,
            lambda: self.chat_scroll.verticalScrollBar().setValue(
                self.chat_scroll.verticalScrollBar().maximum()
            ),
        )

    # ── Async runner ─────────────────────────────────────────────────────────

    def _run_async(self, callback: Any, on_success: Any, on_error: Any | None = None) -> None:
        thread = QThread(self)
        worker = FunctionWorker(callback)
        worker.moveToThread(thread)

        def cleanup() -> None:
            if (thread, worker) in self._active_workers:
                self._active_workers.remove((thread, worker))
            worker.deleteLater()
            thread.quit()

        worker.finished.connect(on_success)
        worker.failed.connect(on_error or self._show_error)
        worker.finished.connect(cleanup)
        worker.failed.connect(cleanup)
        thread.finished.connect(thread.deleteLater)
        thread.started.connect(worker.run)

        self._active_workers.append((thread, worker))
        thread.start()

    # ── File selection ────────────────────────────────────────────────────────

    def _select_audio_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select audio file", "",
            "Audio Files (*.mp3 *.wav *.m4a *.ogg *.flac *.aac);;All Files (*)",
        )
        if not path:
            return
        self._selected_audio_path = path
        short = path.split("/")[-1]
        self.audio_file_label.setText(f"Selected: {short}")
        self.audio_drop_zone.setStyleSheet(
            f"QFrame {{ background: {ACCENT_S}; border: 1.5px dashed {ACCENT}; border-radius: 14px; }}"
        )

    def _select_audio_documents(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select documents", "",
            "Documents (*.pdf *.txt *.docx *.md);;All Files (*)",
        )
        if not paths:
            return
        self._selected_audio_documents = paths
        self._set_list_items(self.audio_docs_list, [p.split("/")[-1] for p in paths])

    def _select_documents_for_upload(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select documents", "",
            "Documents (*.pdf *.txt *.docx *.md);;All Files (*)",
        )
        if not paths:
            return
        self._selected_document_paths = paths
        self._set_list_items(self.selected_documents_list, [p.split("/")[-1] for p in paths])

    # ── Actions ───────────────────────────────────────────────────────────────

    def _start_audio_pipeline(self) -> None:
        if not self._selected_audio_path:
            QMessageBox.warning(self, "Missing audio", "Select an audio file first.")
            return

        audio_path = self._selected_audio_path
        title = self.audio_title_input.text().strip()
        optional_docs = list(self._selected_audio_documents)

        self.start_pipeline_button.setEnabled(False)
        self.progress_widget.show()
        self.statusBar().showMessage("Processing audio and transcription…")

        def task() -> dict[str, int]:
            audio_id = self.transcription_service.process_audio(audio_path, title)
            for p in optional_docs:
                self.document_service.store_document(p, audio_id=audio_id)
            return {"audio_id": audio_id, "document_count": len(optional_docs)}

        def on_success(result: dict[str, int]) -> None:
            self.start_pipeline_button.setEnabled(True)
            self.progress_widget.hide()
            self._selected_audio_path = None
            self._selected_audio_documents = []
            self.audio_file_label.setText("No file selected")
            self.audio_title_input.clear()
            self._set_list_items(self.audio_docs_list, [])
            self._refresh_all()
            self.statusBar().showMessage("Audio processed.")
            QMessageBox.information(
                self, "Done",
                f"Audio stored (ID {result['audio_id']}). "
                f"Documents processed: {result['document_count']}.",
            )

        def on_error(msg: str) -> None:
            self.start_pipeline_button.setEnabled(True)
            self.progress_widget.hide()
            self._show_error(msg)

        self._run_async(task, on_success, on_error)

    def _upload_selected_documents(self) -> None:
        if not self._selected_document_paths:
            QMessageBox.warning(self, "Missing documents", "Select one or more documents first.")
            return

        paths = list(self._selected_document_paths)
        audio_id = self._combo_audio_id(self.document_audio_link_combo)
        self.upload_documents_button.setEnabled(False)
        self.statusBar().showMessage("Uploading documents…")

        def task() -> int:
            for p in paths:
                self.document_service.store_document(p, audio_id=audio_id)
            return len(paths)

        def on_success(count: int) -> None:
            self.upload_documents_button.setEnabled(True)
            self._selected_document_paths = []
            self._set_list_items(self.selected_documents_list, [])
            self._refresh_all()
            self.statusBar().showMessage("Documents uploaded.")
            QMessageBox.information(self, "Done", f"Stored {count} document(s).")

        def on_error(msg: str) -> None:
            self.upload_documents_button.setEnabled(True)
            self._show_error(msg)

        self._run_async(task, on_success, on_error)

    def _generate_notes(self) -> None:
        audio_id = self._combo_audio_id(self.notes_audio_combo)
        if audio_id is None:
            QMessageBox.warning(self, "Missing audio", "Select an audio item first.")
            return

        mode = str(self.notes_mode_combo.currentData())
        self.generate_notes_button.setEnabled(False)
        self.statusBar().showMessage("Generating notes…")

        def task() -> str:
            return self.notes_service.generate_notes(audio_id=audio_id, mode=mode)

        def on_success(notes: str) -> None:
            self.generate_notes_button.setEnabled(True)
            self.notes_output.setPlainText(notes)
            self.statusBar().showMessage("Notes generated.")

        def on_error(msg: str) -> None:
            self.generate_notes_button.setEnabled(True)
            self._show_error(msg)

        self._run_async(task, on_success, on_error)

    def _send_chat_message(self) -> None:
        question = self.chat_input.toPlainText().strip()
        if not question:
            return

        audio_id = self._combo_audio_id(self.chat_audio_combo)
        self._add_chat_bubble(question, is_user=True)
        self.chat_input.clear()
        self.send_chat_button.setEnabled(False)
        self.statusBar().showMessage("Generating response…")

        def task() -> dict[str, object]:
            return self.rag_service.answer_question(question=question, audio_id=audio_id)

        def on_success(result: dict[str, object]) -> None:
            self.send_chat_button.setEnabled(True)
            self._add_chat_bubble(str(result.get("answer", "")), is_user=False)
            sources = result.get("sources", [])
            self.chat_sources_label.setText("  ·  ".join(str(s) for s in sources))
            self.statusBar().showMessage("Ready.")

        def on_error(msg: str) -> None:
            self.send_chat_button.setEnabled(True)
            self._add_chat_bubble(f"Error: {msg}", is_user=False)
            self._show_error(msg)

        self._run_async(task, on_success, on_error)

    def _clear_chat(self) -> None:
        while self.chat_layout.count() > 1:
            item = self.chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                sub = item.layout()
                while sub.count():
                    s = sub.takeAt(0)
                    if s.widget():
                        s.widget().deleteLater()
                sub.deleteLater()
        self.chat_sources_label.clear()

    # ── Data helpers ──────────────────────────────────────────────────────────

    def _load_selected_transcript(self) -> None:
        audio_id = self._combo_audio_id(self.audio_selector_combo)
        if audio_id is None:
            self.raw_transcript_text.clear()
            self.corrected_transcript_text.clear()
            return

        transcript = self.database.get_transcript_by_audio(audio_id)
        if transcript is None:
            self.raw_transcript_text.setPlainText("No transcript available yet.")
            self.corrected_transcript_text.setPlainText("No corrected transcript available yet.")
            return

        self.raw_transcript_text.setPlainText(str(transcript.get("raw_text", "")))
        self.corrected_transcript_text.setPlainText(str(transcript.get("corrected_text", "")))

    def _refresh_documents_table(self) -> None:
        documents = self.database.list_documents()
        self.documents_table.setRowCount(len(documents))
        self._documents_cache = {}

        for row, doc in enumerate(documents):
            doc_id = int(doc["id"])
            self._documents_cache[doc_id] = doc
            linked = doc.get("audio_title") or "—"
            preview = str(doc.get("extracted_text", ""))[:120] + "…"

            self.documents_table.setItem(row, 0, QTableWidgetItem(str(doc.get("original_filename", ""))))
            self.documents_table.setItem(row, 1, QTableWidgetItem(str(linked)))
            self.documents_table.setItem(row, 2, QTableWidgetItem(preview))
            self.documents_table.setItem(row, 3, QTableWidgetItem(str(doc.get("created_at", ""))[:10]))

        if documents:
            self.documents_table.selectRow(0)

    def _show_selected_document_text(self) -> None:
        rows = self.documents_table.selectionModel().selectedRows()
        if not rows:
            self.document_text_preview.clear()
            return

        id_item = self.documents_table.item(rows[0].row(), 0)
        if id_item is None:
            return

        # match by filename to cache
        filename = id_item.text()
        doc = next((d for d in self._documents_cache.values() if str(d.get("original_filename", "")) == filename), None)
        if doc:
            self.document_text_preview.setPlainText(str(doc.get("extracted_text", "")))

    def _load_latest_note(self) -> None:
        audio_id = self._combo_audio_id(self.notes_audio_combo)
        if audio_id is None:
            self.notes_output.clear()
            return

        mode = str(self.notes_mode_combo.currentData())
        note = self.database.get_latest_note(audio_id=audio_id, mode=mode)
        self.notes_output.setPlainText(
            str(note.get("content", "")) if note else "No notes generated yet."
        )

    def _refresh_audio_combos(self) -> None:
        audios = self.database.list_audios()

        prev_ids = {
            "selector": self._combo_audio_id(self.audio_selector_combo),
            "notes": self._combo_audio_id(self.notes_audio_combo),
            "doc_link": self._combo_audio_id(self.document_audio_link_combo),
            "chat": self._combo_audio_id(self.chat_audio_combo),
        }

        combos = [
            self.audio_selector_combo,
            self.notes_audio_combo,
            self.document_audio_link_combo,
            self.chat_audio_combo,
        ]

        for c in combos:
            c.blockSignals(True)
            c.clear()

        self.document_audio_link_combo.addItem("No linked audio", None)
        self.chat_audio_combo.addItem("All sessions", None)

        for audio in audios:
            aid = int(audio["id"])
            label = f"{aid} — {audio.get('title', f'Audio {aid}')}"
            for c in combos:
                c.addItem(label, aid)

        for c in combos:
            c.blockSignals(False)

        keys = ["selector", "notes", "doc_link", "chat"]
        for c, k in zip(combos, keys):
            self._restore_combo_selection(c, prev_ids[k])

    def _refresh_all(self) -> None:
        self._refresh_audio_combos()
        self._load_selected_transcript()
        self._refresh_documents_table()
        self._load_latest_note()

    def _restore_combo_selection(self, combo: QComboBox, value: int | None) -> None:
        if combo.count() == 0:
            return
        idx = combo.findData(value)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    def _combo_audio_id(self, combo: QComboBox) -> int | None:
        data = combo.currentData()
        try:
            return int(data) if data is not None else None
        except (TypeError, ValueError):
            return None

    def _set_list_items(self, lw: QListWidget, values: list[str]) -> None:
        lw.clear()
        for v in values:
            lw.addItem(v)

    def _show_error(self, message: str) -> None:
        self.statusBar().showMessage("Operation failed.")
        QMessageBox.critical(self, "Error", message)

    def closeEvent(self, event: QCloseEvent) -> None:
        for thread, _ in list(self._active_workers):
            thread.quit()
            thread.wait(2000)
        super().closeEvent(event)