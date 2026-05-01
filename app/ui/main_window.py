from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional
from app.ui.workers import TranscriptionWorker

from PyQt6.QtCore import (
    Qt,
    QThread,
    QTimer,
    QSize,
    QPointF,
    pyqtSignal,
    QElapsedTimer,
    QUrl,
    QDateTime,
)
from PyQt6.QtGui import QCloseEvent, QColor, QPalette, QFont, QIcon, QPainter, QPen

from PyQt6.QtMultimedia import (
    QMediaPlayer,
    QAudioOutput,
    QMediaRecorder,
    QMediaCaptureSession,
    QAudioInput,
    QMediaDevices,
    QMediaFormat,
)
from PyQt6.QtMultimediaWidgets import QVideoWidget
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
    QSlider,
)


from app.database import Database
from app.services.api_status_service import ApiHealthStatus, ApiStatusService
from app.services.document_service import DocumentService
from app.services.notes_service import (
    NOTE_MODE_EXACT,
    NOTE_MODE_REFORMULATED,
    NotesService,
)
from app.services.rag_service import RagService
from app.services.transcription_service import TranscriptionService
from app.ui.workers import FunctionWorker

# ── Palette ────────────────────────────────────────────────────────────────────
BG0 = "#0a0b0f"  # deepest — slightly cooler/darker for more contrast
BG1 = "#111318"  # sidebar — more separation from BG0
BG2 = "#1a1d26"  # cards / panels
BG3 = "#22263200"  # inputs / rows — more visible lift

BORDER = "rgba(255,255,255,0.11)"  # was 0.07 — nearly invisible, bumped up
BORDER2 = "rgba(255,255,255,0.20)"  # was 0.13 — input/panel borders need this

TEXT = "#f0f2fa"  # slightly brighter primary text
TEXT2 = "#c4c7dc"  # was #8b8fa8 — body text, much more readable
TEXT3 = "#7a7f9a"  # was #555a70 — hints/meta, visible but clearly secondary

ACCENT = "#6b6ef9"  # unchanged — works well
ACCENT2 = "#9091fb"  # slightly brighter for hover/active states
ACCENT_S = "rgba(107,110,249,0.15)"  # was 0.12
ACCENT_G = "rgba(107,110,249,0.30)"  # was 0.25

GREEN = "#2ecc8f"  # slightly more saturated
GREEN_S = "rgba(46,204,143,0.13)"

AMBER = "#f5a623"  # warmer amber, more distinct
AMBER_S = "rgba(245,166,35,0.12)"

RED = "#fc6b6b"  # slightly brighter red
RED_S = "rgba(252,107,107,0.13)"


def css_border(color: str = BORDER) -> str:
    return f"border: 1px solid {color};"


# ── Reusable styled widgets ────────────────────────────────────────────────────


class StyledButton(QPushButton):
    """Primary (filled) or ghost (outlined) push button."""

    def __init__(
        self, text: str, primary: bool = False, parent: QWidget | None = None
    ) -> None:
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

    def __init__(
        self, text: str = "", color: str = TEXT3, parent: QWidget | None = None
    ) -> None:
        super().__init__(text, parent)
        self.setStyleSheet(
            f"color: {color}; font-family: 'Courier New', monospace; font-size: 11px;"
        )


class SectionLabel(QLabel):
    """Uppercase monospace section header."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text.upper(), parent)
        self.setStyleSheet(
            f"color: {TEXT3}; font-family: 'Courier New', monospace; "
            f"font-size: 10px; letter-spacing: 1px;"
        )


class AttachmentChip(QFrame):
    """Compact removable attachment indicator used by upload flows."""

    remove_requested = pyqtSignal(str)

    def __init__(
        self, file_path: str, kind: str, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.file_path = file_path
        self.kind = kind

        self.setStyleSheet(
            f"background: {BG2}; border: 1px solid {BORDER2}; border-radius: 10px;"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 5, 6, 5)
        lay.setSpacing(8)

        icon = QLabel(self._icon_text())
        icon.setFixedSize(22, 18)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            f"background: {BG3}; color: {ACCENT2}; border-radius: 6px; "
            f"font-size: 9px; font-family: 'Courier New', monospace;"
        )

        name = QLabel(Path(file_path).name)
        name.setStyleSheet(f"color: {TEXT2}; font-size: 12px; background: transparent;")
        name.setToolTip(file_path)

        remove_btn = QPushButton("✕")
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.setFixedSize(18, 18)
        remove_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {TEXT3}; border: none; font-size: 11px; }}"
            f"QPushButton:hover {{ color: {RED}; }}"
        )
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self.file_path))

        lay.addWidget(icon)
        lay.addWidget(name, 1)
        lay.addWidget(remove_btn)

    def _icon_text(self) -> str:
        if self.kind == "audio":
            return "AUD"

        ext = Path(self.file_path).suffix.lower()
        if ext == ".pdf":
            return "PDF"
        if ext in {".doc", ".docx"}:
            return "DOC"
        if ext in {".txt", ".md"}:
            return "TXT"
        return "FILE"


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

    def __init__(
        self,
        title: str,
        tag: str = "",
        tag_live: bool = False,
        parent: QWidget | None = None,
    ) -> None:
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
        header.setStyleSheet(
            f"background: transparent; border-bottom: 1px solid {BORDER};"
        )
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(16, 10, 16, 10)

        title_lbl = MonoLabel(title, TEXT2)
        hlay.addWidget(title_lbl)
        hlay.addStretch()

        if tag:
            tag_bg = GREEN_S if tag_live else BG3
            tag_col = GREEN if tag_live else TEXT3
            tag_lbl = MonoLabel(tag, tag_col)
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


class UploadIcon(QWidget):
    """Outlined upload glyph inside a rounded icon container."""

    def __init__(self, compact: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        size = 36 if compact else 44
        self.setFixedSize(size, size)
        self.setStyleSheet(
            f"background: {BG2}; border: 1px solid {BORDER2}; border-radius: 12px;"
        )

    def paintEvent(self, event: Any) -> None:
        super().paintEvent(event)

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        pen = QPen(QColor(ACCENT2))
        pen.setWidth(2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)

        w = float(self.width())
        h = float(self.height())

        # Arrow shaft + head
        p.drawLine(QPointF(w * 0.50, h * 0.26), QPointF(w * 0.50, h * 0.62))
        p.drawLine(QPointF(w * 0.50, h * 0.26), QPointF(w * 0.36, h * 0.40))
        p.drawLine(QPointF(w * 0.50, h * 0.26), QPointF(w * 0.64, h * 0.40))

        # Tray line
        p.drawLine(QPointF(w * 0.30, h * 0.74), QPointF(w * 0.70, h * 0.74))
        p.drawLine(QPointF(w * 0.30, h * 0.74), QPointF(w * 0.30, h * 0.62))
        p.drawLine(QPointF(w * 0.70, h * 0.74), QPointF(w * 0.70, h * 0.62))


class UploadDropZone(QFrame):
    def __init__(
        self,
        title: str,
        subtitle: str,
        formats: list[str] | None = None,
        compact: bool = False,
        parent: QWidget | None = None,
    ) -> None:
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
        self._compact_row: QHBoxLayout | None = None

        lay = QVBoxLayout(self)
        if compact:
            lay.setContentsMargins(18, 14, 18, 14)
            lay.setSpacing(6)

            row = QHBoxLayout()
            row.setSpacing(10)
            self._compact_row = row
            icon_box = self._make_icon_box(compact=True)
            row.addWidget(icon_box)

            text_col = QVBoxLayout()
            t = QLabel(title)
            t.setStyleSheet(
                f"color: {TEXT}; font-size: 13px; font-weight: 600; border: none; background: transparent;"
            )
            s = QLabel(subtitle)
            s.setStyleSheet(
                f"color: {TEXT3}; font-size: 11px; border: none; background: transparent;"
            )
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
            lay.addWidget(icon_box, alignment=Qt.AlignmentFlag.AlignHCenter)
            lay.addSpacing(14)

            t = QLabel(title)
            t.setStyleSheet(
                f"color: {TEXT}; font-size: 14px; font-weight: 600; border: none; background: transparent;"
            )
            t.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(t)

            s = QLabel(subtitle)
            s.setStyleSheet(
                f"color: {TEXT3}; font-size: 12px; border: none; background: transparent;"
            )
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

    def _make_icon_box(self, compact: bool = False) -> QWidget:
        return UploadIcon(compact=compact)

    def set_compact_action_widget(self, widget: QWidget) -> None:
        if self._compact_row is None:
            return
        self._compact_row.addWidget(widget)

    def enterEvent(self, event: Any) -> None:
        self.setStyleSheet(self._hover_style)

    def leaveEvent(self, event: Any) -> None:
        self.setStyleSheet(self._normal_style)


# ── Nav item ──────────────────────────────────────────────────────────────────


class NavItem(QWidget):
    def __init__(
        self,
        icon_text: str,
        label: str,
        badge: str = "",
        on_click: Callable[[NavItem], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._active = False
        self._on_click = on_click
        self._token_icon = len(icon_text.strip()) > 1

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(10, 8, 10, 8)
        self._layout.setSpacing(10)

        self._icon = QLabel(icon_text)
        self._icon.setFixedSize(30 if self._token_icon else 18, 18)
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon.setStyleSheet(self._icon_style(active=False))

        self._label = QLabel(label)
        self._label.setStyleSheet(
            f"color: {TEXT2}; font-size: 13px; background: transparent; border: none;"
        )

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

    def _icon_style(self, active: bool) -> str:
        if self._token_icon:
            fg = ACCENT2 if active else TEXT2
            bg = ACCENT_G if active else BG3
            return (
                f"color: {fg}; background: {bg}; border: none; border-radius: 6px; "
                f"font-size: 9px; font-family: 'Courier New', monospace; font-weight: 600;"
            )

        color = ACCENT2 if active else TEXT2
        return (
            f"color: {color}; font-size: 14px; background: transparent; border: none;"
        )

    def _set_style(self, active: bool) -> None:
        if active:
            self.setStyleSheet(
                f"QWidget {{ background: {ACCENT_S}; border: 1px solid {ACCENT_G}; border-radius: 10px; }}"
            )
            self._label.setStyleSheet(
                f"color: {ACCENT2}; font-size: 13px; background: transparent; border: none;"
            )
            self._icon.setStyleSheet(self._icon_style(active=True))
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
            self._label.setStyleSheet(
                f"color: {TEXT2}; font-size: 13px; background: transparent; border: none;"
            )
            self._icon.setStyleSheet(self._icon_style(active=False))
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
            if self._on_click is not None:
                self._on_click(self)
                event.accept()
                return

            # Fallback for legacy usage: find a parent widget that handles nav clicks.
            parent = self.parentWidget()
            while parent is not None:
                handler = getattr(parent, "_on_nav_click", None)
                if callable(handler):
                    handler(self)
                    event.accept()
                    return
                parent = parent.parentWidget()

        super().mousePressEvent(event)


# ── Main Window ───────────────────────────────────────────────────────────────


class MainWindow(QMainWindow):
    def __init__(
        self,
        database: Database,
        transcription_service: TranscriptionService,
        document_service: DocumentService,
        notes_service: NotesService,
        rag_service: RagService,
        api_status_service: ApiStatusService,
    ) -> None:
        super().__init__()
        self.database = database
        self.transcription_service = transcription_service
        self.document_service = document_service
        self.notes_service = notes_service
        self.rag_service = rag_service
        self.api_status_service = api_status_service

        # Audio player references
        self.audio_player = None
        self.audio_output = None
        self.play_pause_btn = None
        self.position_slider = None
        self.time_label_player = None

        # Recording members
        self.recorder = None
        self.capture_session = None
        self.recorded_file_path = None
        self.recording_elapsed_timer = None
        self.recording_timer = None
        self.rec_device_combo = None
        self.available_audio_inputs = []

        self.selected_audio_device = None

        self._active_workers: list[tuple[QThread, FunctionWorker]] = []

        # UX decision: one audio per transcription job (clear mapping), multiple docs as attachments.
        self._selected_audio_path: str | None = None
        self._selected_audio_documents: list[str] = []
        self._selected_document_paths: list[str] = []

        self._documents_cache: dict[int, dict[str, Any]] = {}
        self._documents_row_cache: dict[int, dict[str, Any]] = {}
        self._nav_items: list[NavItem] = []

        # New spinner and real progress timers
        self._spinner_timer = None
        self._time_update_timer = None
        self._stage_elapsed_timer = None
        self._spinner_frames = ["◐", "◓", "◑", "◒"]
        self._spinner_index = 0

        self._api_status_check_inflight = False
        self._api_status_timer = QTimer(self)
        self._api_status_timer.setInterval(20000)
        self._api_status_timer.timeout.connect(self._check_api_health)

        self.setWindowTitle("OmniScribe")
        self.resize(1280, 820)
        self.setMinimumSize(960, 640)

        # Global app style (unchanged)
        self.setStyleSheet(f"""
            QMainWindow {{ background: {BG0}; }}
            QWidget {{ background: {BG0}; color: {TEXT}; font-family: 'Segoe UI', 'SF Pro Display', sans-serif; }}
            QScrollBar:vertical {{
                background: transparent; width: 4px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {BG3}; border-radius: 99px; min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {TEXT3}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar:horizontal {{
                background: transparent; height: 4px; margin: 0;
            }}
            QScrollBar::handle:horizontal {{
                background: {BG3}; border-radius: 99px; min-width: 20px;
            }}
            QScrollBar::handle:horizontal:hover {{ background: {TEXT3}; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
            QStatusBar {{ background: {BG1}; color: {TEXT3}; font-size: 11px; border-top: 1px solid {BORDER}; }}
        """)

        self._build_ui()
        self._refresh_attachment_views()
        self._setup_api_status_checks()
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
        self.stack.addWidget(self._build_audio_page())  # 0
        self.stack.addWidget(self._build_documents_page())  # 1
        self.stack.addWidget(self._build_notes_page())  # 2
        self.stack.addWidget(self._build_chat_page())  # 3
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
        logo_widget.setStyleSheet(
            f"background: transparent; border-bottom: 1px solid {BORDER};"
        )
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
        name_lbl.setStyleSheet(
            f"color: {TEXT}; font-size: 15px; font-weight: 700; background: transparent; border: none;"
        )
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
            ("🗎", "Documents", "7"),
            ("📋", "Notes", ""),
            ("🗫", "AI Chat", ""),
        ]
        for icon, label, badge in items:
            item = NavItem(icon, label, badge, on_click=self._on_nav_click)
            nav_lay.addWidget(item)
            self._nav_items.append(item)

        nav_lay.addStretch()
        lay.addWidget(nav_container, 1)

        # Footer status
        footer = QWidget()
        footer.setStyleSheet(
            f"background: transparent; border-top: 1px solid {BORDER};"
        )
        f_lay = QVBoxLayout(footer)
        f_lay.setContentsMargins(10, 12, 10, 12)

        status_pill = QWidget()
        self.api_status_pill = status_pill
        status_pill.setStyleSheet(f"background: {AMBER_S}; border-radius: 10px;")
        sp_lay = QHBoxLayout(status_pill)
        sp_lay.setContentsMargins(10, 8, 10, 8)
        sp_lay.setSpacing(8)

        dot = QLabel("●")
        self.api_status_dot = dot
        dot.setStyleSheet(
            f"color: {AMBER}; font-size: 10px; background: transparent; border: none;"
        )
        status_text = MonoLabel("Connecting...", AMBER)
        self.api_status_text = status_text
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

    def _setup_api_status_checks(self) -> None:
        self._apply_api_status(
            ApiHealthStatus(state="loading", message="Connecting...")
        )
        self._check_api_health()
        self._api_status_timer.start()

    def _check_api_health(self) -> None:
        if self._api_status_check_inflight:
            return

        self._api_status_check_inflight = True
        self._apply_api_status(
            ApiHealthStatus(state="loading", message="Connecting...")
        )

        def task() -> ApiHealthStatus:
            return self.api_status_service.check_health()

        def on_success(status: ApiHealthStatus) -> None:
            self._api_status_check_inflight = False
            self._apply_api_status(status)

        def on_error(message: str) -> None:
            self._api_status_check_inflight = False
            self._apply_api_status(
                ApiHealthStatus(state="error", message=f"API unavailable: {message}")
            )

        self._run_async(task, on_success, on_error)

    def _apply_api_status(self, status: ApiHealthStatus) -> None:
        if status.state == "ready":
            pill_bg = GREEN_S
            dot_color = GREEN
            text_color = GREEN
        elif status.state == "loading":
            pill_bg = AMBER_S
            dot_color = AMBER
            text_color = AMBER
        else:
            pill_bg = RED_S
            dot_color = RED
            text_color = RED

        self.api_status_pill.setStyleSheet(
            f"background: {pill_bg}; border-radius: 10px;"
        )
        self.api_status_dot.setStyleSheet(
            f"color: {dot_color}; font-size: 10px; background: transparent; border: none;"
        )
        self.api_status_text.setText(status.message)
        self.api_status_text.setStyleSheet(
            f"color: {text_color}; font-family: 'Courier New', monospace; font-size: 11px;"
        )

    # ── Topbar helper ────────────────────────────────────────────────────────

    def _make_topbar(
        self, title: str, subtitle: str, actions: list[QWidget]
    ) -> QWidget:
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
        title_lbl.setStyleSheet(
            f"color: {TEXT}; font-size: 15px; font-weight: 700; background: transparent; border: none;"
        )
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
        lay.setSpacing(2)

        buttons: list[QPushButton] = []

        def activate(idx: int) -> None:
            stack.setCurrentIndex(idx)
            for i, b in enumerate(buttons):
                if i == idx:
                    b.setStyleSheet(
                        f"QPushButton {{ color: {ACCENT2}; background: transparent; border: none; "
                        f"border-bottom: 2px solid {ACCENT}; padding: 14px 16px; "
                        f"font-size: 13px; margin-bottom: -1px; }}"
                        f"QPushButton:hover {{ color: {ACCENT2}; }}"
                    )
                else:
                    b.setStyleSheet(
                        f"QPushButton {{ color: {TEXT3}; background: transparent; border: none; "
                        f"border-bottom: 2px solid transparent; padding: 14px 16px; "
                        f"font-size: 13px; margin-bottom: -1px; }}"
                        f"QPushButton:hover {{ color: {TEXT2}; }}"
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
        upload_btn = StyledButton("Transcribe", primary=True)
        upload_btn.clicked.connect(self._start_audio_pipeline)
        self.start_pipeline_button = upload_btn
        lay.addWidget(
            self._make_topbar(
                "Audio & Transcripts",
                "upload → transcribe → review",
                [refresh_btn, upload_btn],
            )
        )

        # Sub-tabs (store reference for later switching)
        self.audio_sub_stack = QStackedWidget()
        self.audio_sub_stack.currentChanged.connect(self._on_audio_subtab_changed)
        self.audio_sub_stack.setStyleSheet(f"background: {BG0};")
        self.audio_sub_stack.addWidget(self._build_audio_upload_sub())  # index 0
        self.audio_sub_stack.addWidget(self._build_audio_record_sub())  # index 1 (new)
        self.audio_sub_stack.addWidget(self._build_audio_transcripts_sub())  # index 2
        lay.addWidget(
            self._make_subtab_bar(
                ["Upload", "Record", "Transcripts"], self.audio_sub_stack
            )
        )
        lay.addWidget(self.audio_sub_stack, 1)
        return page

    def _on_audio_subtab_changed(self, index: int) -> None:
        if index == 1:  # Record tab
            self._refresh_audio_inputs()

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

        self.audio_attachments_box = QWidget()
        self.audio_attachments_box.setStyleSheet(
            "background: transparent; border: none;"
        )
        self.audio_attachments_layout = QVBoxLayout(self.audio_attachments_box)
        self.audio_attachments_layout.setContentsMargins(0, 0, 0, 0)
        self.audio_attachments_layout.setSpacing(6)
        lay.addWidget(self.audio_attachments_box)

        # Title field
        title_section = QWidget()
        title_section.setStyleSheet("background: transparent;")
        ts_lay = QVBoxLayout(title_section)
        ts_lay.setContentsMargins(0, 0, 0, 0)
        ts_lay.setSpacing(6)
        ts_lay.addWidget(SectionLabel("Lecture Title"))
        self.audio_title_input = StyledInput(
            "e.g. Introduction to Machine Learning — Lecture 3"
        )
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
        docs_drop.mousePressEvent = lambda e: self._select_audio_documents()

        browse_btn = StyledButton("Browse")
        browse_btn.setFixedHeight(32)
        browse_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT2};
                border: 1px solid {BORDER2};
                border-radius: 10px;
                padding: 6px 14px;
                font-size: 12px;
            }}
            QPushButton:hover {{ background: {BG2}; color: {TEXT}; }}
            QPushButton:disabled {{ color: {TEXT3}; }}
        """)
        browse_btn.clicked.connect(self._select_audio_documents)
        docs_drop.set_compact_action_widget(browse_btn)

        ds_lay.addWidget(docs_drop)

        self.audio_docs_attachments_box = QWidget()
        self.audio_docs_attachments_box.setStyleSheet(
            "background: transparent; border: none;"
        )
        self.audio_docs_attachments_layout = QVBoxLayout(
            self.audio_docs_attachments_box
        )
        self.audio_docs_attachments_layout.setContentsMargins(0, 0, 0, 0)
        self.audio_docs_attachments_layout.setSpacing(6)
        ds_lay.addWidget(self.audio_docs_attachments_box)
        lay.addWidget(docs_section)

        # Progress widget (spinner + stage + elapsed time)
        self.progress_widget = QWidget()
        self.progress_widget.setStyleSheet(
            f"background: {ACCENT_S}; border: 1px solid {ACCENT_G}; border-radius: 10px;"
        )
        pw_lay = QHBoxLayout(self.progress_widget)
        pw_lay.setContentsMargins(14, 10, 14, 10)
        pw_lay.setSpacing(12)

        self.spinner_label = QLabel("◐")
        self.spinner_label.setStyleSheet(
            f"color: {ACCENT2}; font-size: 16px; font-family: monospace;"
        )
        self.spinner_label.setFixedWidth(20)

        self.stage_label = QLabel("Preparing…")
        self.stage_label.setStyleSheet(
            f"color: {ACCENT2}; font-size: 12px; font-family: 'Courier New', monospace;"
        )

        self.time_label = QLabel("0.0s")
        self.time_label.setStyleSheet(
            f"color: {ACCENT2}; font-size: 12px; font-family: 'Courier New', monospace;"
        )
        self.time_label.setFixedWidth(50)

        pw_lay.addWidget(self.spinner_label)
        pw_lay.addWidget(self.stage_label, 1)
        pw_lay.addWidget(self.time_label)

        self.progress_widget.hide()
        lay.addWidget(self.progress_widget)

        lay.addStretch()
        scroll.setWidget(inner)
        return scroll

    def _build_audio_record_sub(self) -> QWidget:
        """Sub-tab for in-app microphone recording."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")

        inner = QWidget()
        inner.setStyleSheet(f"background: {BG0};")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(16)

        # ---- Recording controls panel ----
        record_panel = QFrame()
        record_panel.setStyleSheet(f"""
            QFrame {{
                background: {BG1};
                border: 1px solid {BORDER};
                border-radius: 14px;
            }}
        """)
        panel_layout = QVBoxLayout(record_panel)
        panel_layout.setContentsMargins(20, 20, 20, 20)
        panel_layout.setSpacing(14)

        # Title field
        title_section = QWidget()
        ts_lay = QVBoxLayout(title_section)
        ts_lay.setContentsMargins(0, 0, 0, 0)
        ts_lay.setSpacing(6)
        ts_lay.addWidget(SectionLabel("Lecture Title (optional)"))
        self.record_title_input = StyledInput("e.g. Introduction to ML — Lecture 4")
        ts_lay.addWidget(self.record_title_input)
        panel_layout.addWidget(title_section)

        # Timer & control buttons row
        controls_row = QHBoxLayout()
        controls_row.setSpacing(12)

        self.rec_timer_label = QLabel("00:00")
        self.rec_timer_label.setStyleSheet(
            f"color: {TEXT}; font-size: 36px; font-weight: 600; font-family: monospace;"
        )
        self.rec_timer_label.setFixedWidth(120)

        self.record_start_btn = StyledButton("Start Recording", primary=True)
        self.record_start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.record_start_btn.clicked.connect(self._start_recording)

        self.record_stop_btn = StyledButton("Stop Recording")
        self.record_stop_btn.setEnabled(False)
        self.record_stop_btn.clicked.connect(self._stop_recording)

        controls_row.addWidget(self.rec_timer_label)
        controls_row.addStretch()
        controls_row.addWidget(self.record_start_btn)
        controls_row.addWidget(self.record_stop_btn)
        panel_layout.addLayout(controls_row)

        # Status / error label
        self.rec_status_label = MonoLabel("Ready", TEXT3)
        panel_layout.addWidget(self.rec_status_label)

        # Device selector
        device_row = QHBoxLayout()
        device_row.setSpacing(8)
        device_row.addWidget(SectionLabel("Microphone"))
        self.rec_device_combo = StyledCombo()
        self.rec_device_combo.currentIndexChanged.connect(self._on_rec_device_changed)
        device_row.addWidget(self.rec_device_combo, 1)
        panel_layout.addLayout(device_row)

        lay.addWidget(record_panel)
        # Progress widget (same as upload tab)
        self.record_progress_widget = QWidget()
        self.record_progress_widget.setStyleSheet(
            f"background: {ACCENT_S}; border: 1px solid {ACCENT_G}; border-radius: 10px;"
        )
        rpw_lay = QHBoxLayout(self.record_progress_widget)
        rpw_lay.setContentsMargins(14, 10, 14, 10)
        rpw_lay.setSpacing(12)

        self.record_spinner_label = QLabel("◐")
        self.record_spinner_label.setStyleSheet(
            f"color: {ACCENT2}; font-size: 16px; font-family: monospace;"
        )
        self.record_spinner_label.setFixedWidth(20)

        self.record_stage_label = QLabel("Preparing…")
        self.record_stage_label.setStyleSheet(
            f"color: {ACCENT2}; font-size: 12px; font-family: 'Courier New', monospace;"
        )

        self.record_time_label = QLabel("0.0s")
        self.record_time_label.setStyleSheet(
            f"color: {ACCENT2}; font-size: 12px; font-family: 'Courier New', monospace;"
        )
        self.record_time_label.setFixedWidth(50)

        rpw_lay.addWidget(self.record_spinner_label)
        rpw_lay.addWidget(self.record_stage_label, 1)
        rpw_lay.addWidget(self.record_time_label)

        self.record_progress_widget.hide()
        lay.addWidget(self.record_progress_widget)

        lay.addStretch()
        scroll.setWidget(inner)
        return scroll

    def _build_audio_transcripts_sub(self) -> QWidget:
        widget = QWidget()
        widget.setStyleSheet(f"background: {BG0};")
        lay = QVBoxLayout(widget)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(14)

        # Selector row
        selector_row = QHBoxLayout()
        selector_row.setSpacing(10)
        lbl = QLabel("Session")
        lbl.setStyleSheet(f"color: {TEXT2}; font-size: 13px;")
        self.audio_selector_combo = StyledCombo()
        self.audio_selector_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.audio_selector_combo.currentIndexChanged.connect(
            self._load_selected_transcript
        )
        selector_row.addWidget(lbl)
        selector_row.addWidget(self.audio_selector_combo, 1)
        lay.addLayout(selector_row)

        # --- NEW: Audio player widget ---
        player_widget = QWidget()
        player_widget.setStyleSheet(f"background: {BG2}; border-radius: 12px;")
        player_layout = QHBoxLayout(player_widget)
        player_layout.setContentsMargins(12, 8, 12, 8)

        self.play_pause_btn = QPushButton("▶")
        self.play_pause_btn.setFixedSize(32, 32)
        self.play_pause_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_pause_btn.setEnabled(False)
        self.play_pause_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT}; color: white; border: none; border-radius: 16px;
                font-size: 14px;
            }}
            QPushButton:hover {{ background: {ACCENT2}; }}
            QPushButton:disabled {{ background: {BG3}; color: {TEXT3}; }}
        """)
        self.play_pause_btn.clicked.connect(self._toggle_audio_playback)

        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 1000)
        self.position_slider.setEnabled(False)
        self.position_slider.sliderMoved.connect(self._seek_audio)

        self.time_label_player = QLabel("00:00 / 00:00")
        self.time_label_player.setStyleSheet(
            f"color: {TEXT3}; font-size: 11px; font-family: 'Courier New', monospace;"
        )

        player_layout.addWidget(self.play_pause_btn)
        player_layout.addWidget(self.position_slider, 1)
        player_layout.addWidget(self.time_label_player)

        lay.addWidget(player_widget)

        # Initialize media player
        self.audio_output = QAudioOutput()
        self.audio_player = QMediaPlayer()
        self.audio_player.setAudioOutput(self.audio_output)
        self.audio_player.errorOccurred.connect(self._handle_player_error)
        self.audio_player.positionChanged.connect(self._update_position)
        self.audio_player.durationChanged.connect(self._update_duration)
        self.audio_player.playbackStateChanged.connect(self._update_play_button)

        # Two panels row
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

    # ----------------------------------------------------------------------
    # Recording logic
    # ----------------------------------------------------------------------
    def _init_recorder(self) -> None:
        """Set up a brand new QMediaRecorder and capture session."""
        # Force recreate every time to avoid stale state
        if self.recorder:
            self.recorder.deleteLater()
            self.recorder = None
        if self.capture_session:
            self.capture_session.deleteLater()
            self.capture_session = None

        self.capture_session = QMediaCaptureSession()

        # Get the selected device (or default if combo not ready).
        # IMPORTANT: store as self._audio_input — on Linux/GStreamer, a local variable
        # gets garbage-collected by Python before the capture session retains it,
        # causing "No audio input device in capture session" errors.
        if self.selected_audio_device is not None:
            self._audio_input = QAudioInput(self.selected_audio_device)
            if self._audio_input.device().isNull():
                print("WARNING: Selected device is not usable, falling back to default")
                self._audio_input = QAudioInput(QMediaDevices.defaultAudioInput())
        else:
            self._audio_input = QAudioInput(QMediaDevices.defaultAudioInput())

        self.capture_session.setAudioInput(self._audio_input)

        self.recorder = QMediaRecorder()
        self.capture_session.setRecorder(self.recorder)

        fmt = QMediaFormat()
        fmt.setFileFormat(QMediaFormat.FileFormat.Wave)
        self.recorder.setMediaFormat(fmt)

        self.recorder.recorderStateChanged.connect(self._on_recorder_state_changed)
        self.recorder.durationChanged.connect(self._on_recording_duration_changed)
        self.recorder.errorOccurred.connect(self._on_recorder_error)

    def _start_recording(self) -> None:
        self._init_recorder()
        if not self.recorder:
            return

        # Debug: show which device is actually being used
        audio_input = self.capture_session.audioInput()
        if audio_input:
            device = audio_input.device()
            print(f"Using audio device: {device.description()} (id: {device.id()})")
        else:
            print("ERROR: No audio input device in capture session")
            self.rec_status_label.setText(
                "No audio input set. Check microphone selection."
            )
            return

        # Create a unique filename in audio storage directory
        timestamp = QDateTime.currentDateTime().toString("yyyyMMdd_hhmmss")
        filename = f"recording_{timestamp}.wav"
        file_path = self.transcription_service.audio_storage_dir / filename
        self.recorded_file_path = str(file_path)

        self.recorder.setOutputLocation(QUrl.fromLocalFile(self.recorded_file_path))

        # Attempt to start recording
        try:
            self.recorder.record()
        except Exception as e:
            self.rec_status_label.setText(f"Failed to start recording: {e}")
            QMessageBox.warning(self, "Recording Error", str(e))

    def _stop_recording(self) -> None:
        """Stop the active recording."""
        if (
            self.recorder
            and self.recorder.recorderState()
            == QMediaRecorder.RecorderState.RecordingState
        ):
            self.recorder.stop()

    def _on_recorder_state_changed(self, state: QMediaRecorder.RecorderState) -> None:
        if state == QMediaRecorder.RecorderState.RecordingState:
            self.record_start_btn.setEnabled(False)
            self.record_stop_btn.setEnabled(True)
            self.start_pipeline_button.setEnabled(
                False
            )  # disable Transcribe while recording
            self.rec_status_label.setText("Recording...")
            self.recording_elapsed_timer = QElapsedTimer()
            self.recording_elapsed_timer.start()
            self.recording_timer = QTimer()
            self.recording_timer.timeout.connect(self._update_recording_timer)
            self.recording_timer.start(100)
            self.rec_timer_label.setText("00:00")
        elif state == QMediaRecorder.RecorderState.StoppedState:
            self.record_start_btn.setEnabled(True)
            self.record_stop_btn.setEnabled(False)
            if self.recording_timer:
                self.recording_timer.stop()
            if self.recorded_file_path and not Path(self.recorded_file_path).exists():
                self.rec_status_label.setText("Error: recording file not saved.")
                self.start_pipeline_button.setEnabled(False)
            else:
                self.rec_status_label.setText(
                    "Recording finished. Click 'Transcribe' above."
                )
                self.start_pipeline_button.setEnabled(
                    True
                )  # enable top Transcribe button
        elif state == QMediaRecorder.RecorderState.PausedState:
            pass

    def _update_recording_timer(self) -> None:
        if self.recording_elapsed_timer and self.recording_elapsed_timer.isValid():
            elapsed_ms = self.recording_elapsed_timer.elapsed()
            seconds = elapsed_ms // 1000
            minutes = seconds // 60
            seconds = seconds % 60
            self.rec_timer_label.setText(f"{minutes:02d}:{seconds:02d}")

    def _on_recording_duration_changed(self, duration: int) -> None:
        # Duration in milliseconds – we already have our own timer, but can keep for accuracy
        pass

    def _on_recorder_error(
        self, error: QMediaRecorder.Error, error_string: str
    ) -> None:
        if error != QMediaRecorder.Error.NoError:
            self.rec_status_label.setText(f"Recorder error: {error_string}")
            self.record_start_btn.setEnabled(True)
            self.record_stop_btn.setEnabled(False)
            self.start_pipeline_button.setEnabled(False)
            if self.recording_timer:
                self.recording_timer.stop()

    def _transcribe_recorded_audio(self) -> None:
        if not self.recorded_file_path or not Path(self.recorded_file_path).exists():
            QMessageBox.warning(self, "No recording", "No valid recording found.")
            return
        title = self.record_title_input.text().strip()
        self._process_audio_with_pipeline(
            audio_path=self.recorded_file_path,
            title=title,
            doc_paths=[],
        )

    def _refresh_audio_inputs(self) -> None:
        """Refresh the list of available audio input devices."""
        self.available_audio_inputs = QMediaDevices.audioInputs()
        if not self.available_audio_inputs:
            self.rec_status_label.setText(
                "No microphone found. Check system settings and ensure a recording device is available."
            )
            self.record_start_btn.setEnabled(False)
            self.record_stop_btn.setEnabled(False)
            self.transcribe_recording_btn.setEnabled(False)
            if hasattr(self, "rec_device_combo"):
                self.rec_device_combo.clear()
                self.rec_device_combo.addItem("No devices", None)
            return

        self.record_start_btn.setEnabled(True)

        # Populate combo box
        if hasattr(self, "rec_device_combo"):
            self.rec_device_combo.blockSignals(True)
            self.rec_device_combo.clear()
            for i, dev in enumerate(self.available_audio_inputs):
                test_input = QAudioInput(dev)
                if test_input.device().isNull():
                    continue  # skip this device
                description = dev.description().strip()
                if not description:
                    description = f"Device {i+1}"
                self.rec_device_combo.addItem(description, i)
            self.rec_device_combo.blockSignals(False)
            # Select default device
            default_idx = 0
            default_dev = QMediaDevices.defaultAudioInput()
            if default_dev:
                for i, dev in enumerate(self.available_audio_inputs):
                    if dev == default_dev:
                        default_idx = i
                        break
            self.rec_device_combo.setCurrentIndex(default_idx)
            self._on_rec_device_changed(default_idx)

    def _on_rec_device_changed(self, idx: int) -> None:
        if idx < 0 or not self.available_audio_inputs:
            self.selected_audio_device = None
            return
        self.selected_audio_device = self.available_audio_inputs[idx]
        self.rec_status_label.setText(
            f"Microphone: {self.selected_audio_device.description()}"
        )

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

        lay.addWidget(
            self._make_topbar(
                "Documents",
                "select → link → upload",
                [
                    self.document_audio_link_combo,
                    self.select_documents_button,
                    upload_btn,
                ],
            )
        )

        content = QWidget()
        content.setStyleSheet(f"background: {BG0};")
        c_lay = QVBoxLayout(content)
        c_lay.setContentsMargins(24, 18, 24, 18)
        c_lay.setSpacing(14)

        self.documents_upload_attachments_box = QWidget()
        self.documents_upload_attachments_box.setStyleSheet(
            "background: transparent; border: none;"
        )
        self.documents_upload_attachments_layout = QVBoxLayout(
            self.documents_upload_attachments_box
        )
        self.documents_upload_attachments_layout.setContentsMargins(0, 0, 0, 0)
        self.documents_upload_attachments_layout.setSpacing(6)
        c_lay.addWidget(self.documents_upload_attachments_box)

        # Table panel
        table_panel = PanelFrame("stored documents")
        self.documents_table = QTableWidget(0, 4)
        self.documents_table.setHorizontalHeaderLabels(
            ["Filename", "Linked Session", "Preview", "Added"]
        )
        self.documents_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.documents_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.documents_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.documents_table.verticalHeader().setVisible(False)
        self.documents_table.verticalHeader().setDefaultSectionSize(42)
        self.documents_table.horizontalHeader().setStretchLastSection(False)
        self.documents_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Interactive
        )
        self.documents_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.documents_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.documents_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self.documents_table.setColumnWidth(0, 300)
        self.documents_table.setShowGrid(False)
        self.documents_table.setMouseTracking(True)
        self.documents_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.documents_table.setWordWrap(False)
        self.documents_table.setStyleSheet(f"""
            QTableWidget {{
                background: transparent; border: none; color: {TEXT2};
                font-size: 13px; gridline-color: transparent;
            }}
            QTableWidget::item {{
                padding: 10px 14px;
                border-bottom: 1px solid {BORDER};
                color: {TEXT2};
            }}
            QTableWidget::item:hover {{ background: {BG2}; color: {TEXT}; }}
            QTableWidget::item:selected:active, QTableWidget::item:selected:!active {{
                background: {BG2}; color: {TEXT};
            }}
            QHeaderView::section {{
                background: transparent; color: {TEXT3};
                font-size: 10px; font-family: 'Courier New', monospace;
                text-transform: uppercase; letter-spacing: 0.06em;
                padding: 10px 14px; border: none;
                border-bottom: 1px solid {BORDER};
            }}
            QTableCornerButton::section {{ background: transparent; border: none; }}
        """)
        self.documents_table.itemSelectionChanged.connect(
            self._show_selected_document_text
        )
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

        lay.addWidget(
            self._make_topbar(
                "Generated Notes",
                "AI-structured study notes",
                [self.notes_audio_combo, self.notes_mode_combo, load_btn, gen_btn],
            )
        )

        content = QWidget()
        content.setStyleSheet(f"background: {BG0};")
        c_lay = QVBoxLayout(content)
        c_lay.setContentsMargins(24, 18, 24, 18)
        c_lay.setSpacing(0)

        notes_panel = PanelFrame("notes", "generated", tag_live=True)
        self.notes_output = QTextEdit()
        self.notes_output.setReadOnly(True)
        self.notes_output.setStyleSheet(
            f"QTextEdit {{ background: transparent; border: none; color: {TEXT2}; font-size: 13.5px; }}"
        )
        self.notes_output.document().setDefaultStyleSheet(f"""
            h1, h2, h3, h4, h5, h6 {{ color: {TEXT}; margin-top: 12px; margin-bottom: 6px; }}
            p, li {{ color: {TEXT2}; }}
            code {{ background: {BG3}; color: {TEXT}; border-radius: 4px; padding: 1px 4px; }}
            pre {{ background: {BG3}; color: {TEXT}; border: 1px solid {BORDER}; border-radius: 8px; padding: 10px; }}
            """)
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

        lay.addWidget(
            self._make_topbar(
                "AI Chat",
                "RAG over your sessions + docs",
                [self.chat_audio_combo, clear_btn],
            )
        )

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
        sources_wrap = QWidget()
        sources_wrap.setStyleSheet(
            f"background: {BG1}; border-top: 1px solid {BORDER};"
        )
        sw_lay = QHBoxLayout(sources_wrap)
        sw_lay.setContentsMargins(14, 8, 14, 8)
        sw_lay.setSpacing(8)

        src_label = QLabel("sources:")
        src_label.setStyleSheet(
            f"color: {TEXT3}; font-size: 11px; font-family: 'Courier New', monospace;"
        )
        sw_lay.addWidget(src_label)

        self.chat_sources_container = QWidget()
        self.chat_sources_container.setStyleSheet(
            "background: transparent; border: none;"
        )
        self.chat_sources_layout = QHBoxLayout(self.chat_sources_container)
        self.chat_sources_layout.setContentsMargins(0, 0, 0, 0)
        self.chat_sources_layout.setSpacing(8)
        sw_lay.addWidget(self.chat_sources_container, 1)
        lay.addWidget(sources_wrap)
        self._set_chat_sources([])

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

    def _run_async(
        self, callback: Any, on_success: Any, on_error: Any | None = None
    ) -> None:
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
            self,
            "Select audio file",
            "",
            "Audio Files (*.mp3 *.wav *.m4a *.ogg *.flac *.aac);;All Files (*)",
        )
        if not path:
            return

        if self._selected_audio_path and self._selected_audio_path != path:
            choice = QMessageBox.question(
                self,
                "Replace audio attachment?",
                "A different audio file is already attached. Replace it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if choice != QMessageBox.StandardButton.Yes:
                return

        self._selected_audio_path = path
        self.audio_drop_zone.setStyleSheet(
            f"QFrame {{ background: {ACCENT_S}; border: 1.5px dashed {ACCENT}; border-radius: 14px; }}"
        )
        self._refresh_attachment_views()

    def _select_audio_documents(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select documents",
            "",
            "Documents (*.pdf *.txt *.docx *.md);;All Files (*)",
        )
        if not paths:
            return

        self._selected_audio_documents = self._merge_unique_paths(
            self._selected_audio_documents, list(paths)
        )
        self._refresh_attachment_views()

    def _select_documents_for_upload(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select documents",
            "",
            "Documents (*.pdf *.txt *.docx *.md);;All Files (*)",
        )
        if not paths:
            return

        self._selected_document_paths = self._merge_unique_paths(
            self._selected_document_paths, list(paths)
        )
        self._refresh_attachment_views()

    # ── Actions ───────────────────────────────────────────────────────────────

    def _start_audio_pipeline(self) -> None:
        # If we're on the Record tab and have a recorded file, use that
        if (
            hasattr(self, "audio_sub_stack")
            and self.audio_sub_stack.currentIndex() == 1
            and self.recorded_file_path
            and Path(self.recorded_file_path).exists()
        ):
            title = self.record_title_input.text().strip()
            self._process_audio_with_pipeline(
                audio_path=self.recorded_file_path,
                title=title,
                doc_paths=[],
            )
            return

        # Otherwise, normal upload flow
        if not self._selected_audio_path:
            QMessageBox.warning(self, "Missing audio", "Select an audio file first.")
            return
        self._process_audio_with_pipeline(
            audio_path=self._selected_audio_path,
            title=self.audio_title_input.text().strip(),
            doc_paths=list(self._selected_audio_documents),
        )

    def _process_audio_with_pipeline(
        self, audio_path: str, title: str, doc_paths: list[str]
    ) -> None:
        """Common logic to start the transcription worker."""
        self.start_pipeline_button.setEnabled(False)
        self.progress_widget.show()
        self._start_pipeline_progress()
        self.statusBar().showMessage("Processing audio and transcription…")

        self._active_worker_thread = QThread(self)
        self._transcription_worker = TranscriptionWorker(
            transcription_service=self.transcription_service,
            audio_path=audio_path,
            title=title,
            document_paths=doc_paths,
            document_service=self.document_service,
        )
        self._transcription_worker.moveToThread(self._active_worker_thread)

        self._transcription_worker.stage_changed.connect(self._on_transcription_stage)
        self._transcription_worker.finished.connect(self._on_transcription_finished)
        self._transcription_worker.failed.connect(self._on_transcription_failed)

        self._active_worker_thread.started.connect(self._transcription_worker.run)
        self._active_worker_thread.finished.connect(
            self._active_worker_thread.deleteLater
        )

        self._active_worker_thread.start()

    def _start_pipeline_progress(self) -> None:
        self._spinner_index = 0
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(100)
        self._spinner_timer.timeout.connect(self._update_spinner)
        self._spinner_timer.start()

        self._stage_elapsed_timer = QElapsedTimer()
        self._stage_elapsed_timer.start()
        self._time_update_timer = QTimer(self)
        self._time_update_timer.setInterval(100)
        self._time_update_timer.timeout.connect(self._update_pipeline_time)
        self._time_update_timer.start()

        self.stage_label.setText("Preparing…")
        self.time_label.setText("0.0s")

        # Also show on record tab if that's the active sub-tab
        if (
            hasattr(self, "audio_sub_stack")
            and self.audio_sub_stack.currentIndex() == 1
        ):
            self.record_stage_label.setText("Preparing…")
            self.record_time_label.setText("0.0s")
            self.record_spinner_label.setText("◐")
            self.record_progress_widget.show()
        else:
            self.progress_widget.show()

    def _update_spinner(self) -> None:
        self._spinner_index = (self._spinner_index + 1) % len(self._spinner_frames)
        frame = self._spinner_frames[self._spinner_index]
        self.spinner_label.setText(frame)
        if hasattr(self, "record_spinner_label"):
            self.record_spinner_label.setText(frame)

    def _update_pipeline_time(self) -> None:
        if self._stage_elapsed_timer and self._stage_elapsed_timer.isValid():
            elapsed = self._stage_elapsed_timer.elapsed() / 1000.0
            txt = f"{elapsed:.1f}s"
            self.time_label.setText(txt)
            if hasattr(self, "record_time_label"):
                self.record_time_label.setText(txt)

    def _stop_pipeline_progress(self) -> None:
        if self._spinner_timer:
            self._spinner_timer.stop()
            self._spinner_timer = None
        if self._time_update_timer:
            self._time_update_timer.stop()
            self._time_update_timer = None
        self.progress_widget.hide()
        if hasattr(self, "record_progress_widget"):
            self.record_progress_widget.hide()

    def _on_transcription_stage(self, stage: str) -> None:
        if self._stage_elapsed_timer:
            self._stage_elapsed_timer.restart()

        labels = {
            "uploading": "Uploading audio…",
            "transcribing": "Transcribing…",
            "correcting": "Correcting transcript…",
        }
        text = labels.get(stage, stage)
        self.stage_label.setText(text)
        if hasattr(self, "record_stage_label"):
            self.record_stage_label.setText(text)

    def _on_transcription_finished(self, audio_id: int) -> None:
        self._stop_pipeline_progress()
        self.start_pipeline_button.setEnabled(True)

        # Clear selected files and refresh
        self._selected_audio_path = None
        self._selected_audio_documents = []
        self.audio_title_input.clear()
        self._refresh_attachment_views()
        self._refresh_all()

        # Switch to Transcripts sub-tab and select the new audio
        if hasattr(self, "audio_sub_stack"):
            self.audio_sub_stack.setCurrentIndex(2)
        # Select the newly created audio in the combo
        index = self.audio_selector_combo.findData(audio_id)
        if index >= 0:
            self.audio_selector_combo.setCurrentIndex(index)

        self.statusBar().showMessage("Audio processed.")
        QMessageBox.information(
            self,
            "Done",
            f"Audio stored (ID {audio_id}). Documents processed.",
        )

        # Clean up thread
        if hasattr(self, "_active_worker_thread"):
            self._active_worker_thread.quit()
            self._active_worker_thread.wait(2000)

    def _on_transcription_failed(self, message: str) -> None:
        self._stop_pipeline_progress()
        self.start_pipeline_button.setEnabled(True)
        self.statusBar().showMessage("Transcription failed.")
        QMessageBox.critical(self, "Error", message)

        if hasattr(self, "_active_worker_thread"):
            self._active_worker_thread.quit()
            self._active_worker_thread.wait(2000)

    def _merge_unique_paths(
        self, existing: list[str], incoming: list[str]
    ) -> list[str]:
        merged = list(existing)
        seen = {Path(p).resolve() for p in existing}
        for candidate in incoming:
            resolved = Path(candidate).resolve()
            if resolved in seen:
                continue
            merged.append(str(resolved))
            seen.add(resolved)
        return merged

    def _refresh_attachment_views(self) -> None:
        self._render_attachments(
            layout=self.audio_attachments_layout,
            files=[self._selected_audio_path] if self._selected_audio_path else [],
            kind="audio",
            empty_text="No audio attached",
            remove_callback=self._remove_audio_attachment,
        )
        self._render_attachments(
            layout=self.audio_docs_attachments_layout,
            files=self._selected_audio_documents,
            kind="document",
            empty_text="No supporting documents attached",
            remove_callback=self._remove_audio_document_attachment,
        )
        self._render_attachments(
            layout=self.documents_upload_attachments_layout,
            files=self._selected_document_paths,
            kind="document",
            empty_text="No documents selected",
            remove_callback=self._remove_documents_upload_attachment,
        )

    def _render_attachments(
        self,
        *,
        layout: QVBoxLayout,
        files: list[str],
        kind: str,
        empty_text: str,
        remove_callback: Callable[[str], None],
    ) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not files:
            layout.addWidget(MonoLabel(empty_text, TEXT3))
            return

        for file_path in files:
            chip = AttachmentChip(file_path=file_path, kind=kind)
            chip.remove_requested.connect(remove_callback)
            layout.addWidget(chip)

    def _remove_audio_attachment(self, file_path: str) -> None:
        if self._selected_audio_path == file_path:
            self._selected_audio_path = None
            self._refresh_attachment_views()

    def _remove_audio_document_attachment(self, file_path: str) -> None:
        self._selected_audio_documents = [
            p for p in self._selected_audio_documents if p != file_path
        ]
        self._refresh_attachment_views()

    def _remove_documents_upload_attachment(self, file_path: str) -> None:
        self._selected_document_paths = [
            p for p in self._selected_document_paths if p != file_path
        ]
        self._refresh_attachment_views()

    def _upload_selected_documents(self) -> None:
        if not self._selected_document_paths:
            QMessageBox.warning(
                self, "Missing documents", "Select one or more documents first."
            )
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
            self._refresh_attachment_views()
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
            self._set_notes_markdown(notes)
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
            return self.rag_service.answer_question(
                question=question, audio_id=audio_id
            )

        def on_success(result: dict[str, object]) -> None:
            self.send_chat_button.setEnabled(True)
            self._add_chat_bubble(str(result.get("answer", "")), is_user=False)
            raw_sources = result.get("sources", [])
            if isinstance(raw_sources, (list, tuple)):
                sources = [str(s) for s in raw_sources]
            elif raw_sources:
                sources = [str(raw_sources)]
            else:
                sources = []
            self._set_chat_sources(sources)
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
        self._set_chat_sources([])

    def _set_chat_sources(self, sources: list[str]) -> None:
        while self.chat_sources_layout.count():
            item = self.chat_sources_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        unique_sources: list[str] = []
        seen: set[str] = set()
        for source in sources:
            normalized = source.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            unique_sources.append(normalized)

        if not unique_sources:
            empty = QLabel("none")
            empty.setStyleSheet(
                f"color: {TEXT3}; font-size: 11px; font-family: 'Courier New', monospace;"
            )
            self.chat_sources_layout.addWidget(empty)
            self.chat_sources_layout.addStretch()
            return

        def display_label(source: str) -> str:
            if source.startswith("Transcript - "):
                return f"transcript:{source.removeprefix('Transcript - ')}"
            if source.startswith("Document - "):
                return source.removeprefix("Document - ")
            return source

        for source in unique_sources:
            chip = QLabel(display_label(source))
            chip.setStyleSheet(
                f"color: {ACCENT2}; background: {ACCENT_S}; "
                f"border: 1px solid {ACCENT_G}; border-radius: 99px; "
                f"padding: 3px 9px; font-size: 11px; font-family: 'Courier New', monospace;"
            )
            self.chat_sources_layout.addWidget(chip)

        self.chat_sources_layout.addStretch()

    def _make_file_icon(self, filename: str) -> QLabel:
        ext = filename.split(".")[-1].lower() if "." in filename else ""
        if ext == "pdf":
            tag = "PDF"
            bg = "rgba(248,113,113,0.15)"
            fg = RED
        elif ext in {"doc", "docx"}:
            tag = "DOC"
            bg = "rgba(52,211,153,0.10)"
            fg = GREEN
        elif ext in {"txt", "md"}:
            tag = "TXT"
            bg = ACCENT_S
            fg = ACCENT2
        else:
            tag = ext[:4].upper() if ext else "FILE"
            bg = BG3
            fg = TEXT2

        icon = QLabel(tag)
        icon.setFixedSize(22, 22)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            f"background: {bg}; color: {fg}; border-radius: 5px; "
            f"font-size: 9px; font-family: 'Courier New', monospace; font-weight: 600;"
        )
        return icon

    def _make_filename_cell(self, filename: str) -> QWidget:
        cell = QWidget()
        cell.setStyleSheet("background: transparent; border: none;")
        lay = QHBoxLayout(cell)
        lay.setContentsMargins(14, 4, 14, 4)
        lay.setSpacing(8)
        lay.addWidget(self._make_file_icon(filename))

        name = QLabel(filename)
        name.setStyleSheet(
            f"color: {TEXT2}; font-size: 13px; background: transparent; border: none;"
        )
        lay.addWidget(name, 1)
        return cell

    def _make_linked_cell(self, linked: str) -> QWidget:
        cell = QWidget()
        cell.setStyleSheet("background: transparent; border: none;")
        lay = QHBoxLayout(cell)
        lay.setContentsMargins(14, 4, 14, 4)
        lay.setSpacing(0)

        lbl = QLabel(linked)
        if linked != "—":
            lbl.setStyleSheet(
                f"background: {AMBER_S}; color: {AMBER}; border-radius: 99px; "
                f"padding: 2px 8px; font-size: 10px; font-family: 'Courier New', monospace;"
            )
        else:
            lbl.setStyleSheet(
                f"color: {TEXT3}; font-size: 13px; background: transparent; border: none;"
            )

        lay.addWidget(
            lbl, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        lay.addStretch()
        return cell

    # ── Data helpers ──────────────────────────────────────────────────────────

    def _load_selected_transcript(self) -> None:
        audio_id = self._combo_audio_id(self.audio_selector_combo)
        if audio_id is None:
            self.raw_transcript_text.clear()
            self.corrected_transcript_text.clear()
            self._update_player_for_selected_audio(None)
            return

        transcript = self.database.get_transcript_by_audio(audio_id)
        if transcript is None:
            self.raw_transcript_text.setPlainText("No transcript available yet.")
            self.corrected_transcript_text.setPlainText(
                "No corrected transcript available yet."
            )
        else:
            self.raw_transcript_text.setPlainText(str(transcript.get("raw_text", "")))
            self.corrected_transcript_text.setPlainText(
                str(transcript.get("corrected_text", ""))
            )

        self._update_player_for_selected_audio(audio_id)

    # Player control methods
    def _update_player_for_selected_audio(self, audio_id: Optional[int]) -> None:
        if audio_id is None:
            self.play_pause_btn.setEnabled(False)
            self.position_slider.setEnabled(False)
            self.time_label_player.setText("00:00 / 00:00")
            if (
                self.audio_player.playbackState()
                != QMediaPlayer.PlaybackState.StoppedState
            ):
                self.audio_player.stop()
            return

        # Get stored_path from database
        with self.database._connect() as conn:
            row = conn.execute(
                "SELECT stored_path FROM audios WHERE id = ?", (audio_id,)
            ).fetchone()
        if not row:
            self.play_pause_btn.setEnabled(False)
            self.position_slider.setEnabled(False)
            self.time_label_player.setText("File missing")
            return

        stored_path = row["stored_path"]
        if not Path(stored_path).exists():
            self.play_pause_btn.setEnabled(False)
            self.position_slider.setEnabled(False)
            self.time_label_player.setText("File missing")
            return

        # Stop current playback and load new source
        self.audio_player.stop()
        self.audio_player.setSource(QUrl.fromLocalFile(stored_path))
        self.play_pause_btn.setEnabled(True)
        self.position_slider.setEnabled(True)
        self.position_slider.setValue(0)
        self.time_label_player.setText("00:00 / 00:00")

    def _toggle_audio_playback(self) -> None:
        if self.audio_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.audio_player.pause()
        else:
            self.audio_player.play()

    def _seek_audio(self, position: int) -> None:
        duration = self.audio_player.duration()
        if duration > 0:
            self.audio_player.setPosition(int(position / 1000.0 * duration))

    def _update_position(self, position: int) -> None:
        if not self.position_slider.isSliderDown():
            duration = self.audio_player.duration()
            if duration > 0:
                self.position_slider.setValue(int(position / duration * 1000))
        # Update time label
        pos_secs = position // 1000
        dur_secs = self.audio_player.duration() // 1000
        pos_str = f"{pos_secs//60:02d}:{pos_secs%60:02d}"
        dur_str = f"{dur_secs//60:02d}:{dur_secs%60:02d}"
        self.time_label_player.setText(f"{pos_str} / {dur_str}")

    def _update_duration(self, duration: int) -> None:
        if duration > 0:
            dur_secs = duration // 1000
            dur_str = f"{dur_secs//60:02d}:{dur_secs%60:02d}"
            pos_secs = self.audio_player.position() // 1000
            pos_str = f"{pos_secs//60:02d}:{pos_secs%60:02d}"
            self.time_label_player.setText(f"{pos_str} / {dur_str}")

    def _update_play_button(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_pause_btn.setText("⏸")
        else:
            self.play_pause_btn.setText("▶")

    def _handle_player_error(
        self, error: QMediaPlayer.Error, error_string: str
    ) -> None:
        if error != QMediaPlayer.Error.NoError:
            self.play_pause_btn.setEnabled(False)
            self.position_slider.setEnabled(False)
            self.time_label_player.setText("Error")
            QMessageBox.warning(self, "Media Player Error", error_string)

    def _refresh_documents_table(self) -> None:
        documents = self.database.list_documents()
        self.documents_table.setRowCount(len(documents))
        self._documents_cache = {}
        self._documents_row_cache = {}

        for row, doc in enumerate(documents):
            doc_id = int(doc["id"])
            self._documents_cache[doc_id] = doc
            self._documents_row_cache[row] = doc

            filename = str(doc.get("original_filename", ""))
            linked = doc.get("audio_title") or "—"
            raw_preview = str(doc.get("extracted_text", "")).replace("\n", " ").strip()
            preview = (
                (raw_preview[:120] + "…") if len(raw_preview) > 120 else raw_preview
            )

            # Keep first two items empty because those columns are fully custom widgets.
            filename_item = QTableWidgetItem("")
            linked_item = QTableWidgetItem("")
            preview_item = QTableWidgetItem(preview)
            added_item = QTableWidgetItem(str(doc.get("created_at", ""))[:10])

            filename_item.setData(Qt.ItemDataRole.UserRole, filename)
            linked_item.setData(Qt.ItemDataRole.UserRole, str(linked))

            for item in (filename_item, linked_item, preview_item, added_item):
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)

            preview_item.setForeground(QColor(TEXT3))
            preview_item.setToolTip(raw_preview)
            added_item.setForeground(QColor(TEXT2))

            self.documents_table.setItem(row, 0, filename_item)
            self.documents_table.setItem(row, 1, linked_item)
            self.documents_table.setItem(row, 2, preview_item)
            self.documents_table.setItem(row, 3, added_item)

            self.documents_table.setCellWidget(
                row, 0, self._make_filename_cell(filename)
            )
            self.documents_table.setCellWidget(
                row, 1, self._make_linked_cell(str(linked))
            )
            self.documents_table.setRowHeight(row, 42)

        if documents:
            self.documents_table.selectRow(0)

    def _show_selected_document_text(self) -> None:
        rows = self.documents_table.selectionModel().selectedRows()
        if not rows:
            self.document_text_preview.clear()
            return

        doc = self._documents_row_cache.get(rows[0].row())
        if doc:
            self.document_text_preview.setPlainText(str(doc.get("extracted_text", "")))

    def _set_notes_markdown(self, content: str) -> None:
        text = content.strip()

        # Some model responses wrap markdown in a fenced block; unwrap it for readable rendering.
        for _ in range(2):
            lines = text.splitlines()
            if (
                len(lines) >= 2
                and lines[0].strip().startswith("```")
                and lines[-1].strip() == "```"
            ):
                text = "\n".join(lines[1:-1]).strip()
            else:
                break

        self.notes_output.setMarkdown(text if text else "No notes generated yet.")

    def _load_latest_note(self) -> None:
        audio_id = self._combo_audio_id(self.notes_audio_combo)
        if audio_id is None:
            self.notes_output.clear()
            return

        mode = str(self.notes_mode_combo.currentData())
        note = self.database.get_latest_note(audio_id=audio_id, mode=mode)
        self._set_notes_markdown(
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

    def _show_error(self, message: str) -> None:
        self.statusBar().showMessage("Operation failed.")
        QMessageBox.critical(self, "Error", message)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._api_status_timer.isActive():
            self._api_status_timer.stop()
        if self._spinner_timer and self._spinner_timer.isActive():
            self._spinner_timer.stop()
        if self._time_update_timer and self._time_update_timer.isActive():
            self._time_update_timer.stop()
        # Stop media player
        if self.audio_player:
            self.audio_player.stop()
        for thread, _ in list(self._active_workers):
            thread.quit()
            thread.wait(2000)
        if (
            self.recorder
            and self.recorder.recorderState()
            == QMediaRecorder.RecorderState.RecordingState
        ):
            self.recorder.stop()
        super().closeEvent(event)
