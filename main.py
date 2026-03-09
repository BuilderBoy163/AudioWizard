import sys
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QStackedWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTextEdit, QPushButton, QFileDialog, QMessageBox,
    QToolBar, QFrame, QSizePolicy, QProgressBar, QDialog,
)
from PySide6.QtGui import QIcon, QAction, QFont, QColor, QPalette
from PySide6.QtCore import (
    Qt, Signal, QThread, QObject, QPropertyAnimation,
    QRect, QAbstractAnimation, QEasingCurve, QSize
)

from encoder import encode_audio
from decoder import decode_audio
from app_settings import SettingsWindow, load_settings

# ─────────────────────────────────────────────────────────────────────────────
# Worker threads (keep UI responsive during encode/decode)
# ─────────────────────────────────────────────────────────────────────────────

class EncodeWorker(QObject):
    finished = Signal(str)   # empty string = success; otherwise error message
    progress = Signal(str)

    def __init__(self, input_file, output_file, message, chunk_ms):
        super().__init__()
        self.input_file  = input_file
        self.output_file = output_file
        self.message     = message
        self.chunk_ms    = chunk_ms

    def run(self):
        try:
            encode_audio(self.input_file, self.output_file, self.message, self.chunk_ms)
            self.finished.emit("")
        except Exception as exc:
            self.finished.emit(str(exc))


class DecodeWorker(QObject):
    finished = Signal(str, str)   # (result, error)

    def __init__(self, input_file, chunk_ms):
        super().__init__()
        self.input_file = input_file
        self.chunk_ms   = chunk_ms

    def run(self):
        try:
            result = decode_audio(self.input_file, self.chunk_ms)
            self.finished.emit(result, "")
        except Exception as exc:
            self.finished.emit("", str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Shared UI helpers
# ─────────────────────────────────────────────────────────────────────────────

class SectionLabel(QLabel):
    def __init__(self, text):
        super().__init__(text)
        self.setStyleSheet(
            "font-size: 11px; font-weight: 700; letter-spacing: 1.5px;"
            "color: rgba(180,180,200,0.8); text-transform: uppercase;"
        )


class Divider(QFrame):
    def __init__(self):
        super().__init__()
        self.setFrameShape(QFrame.HLine)
        self.setStyleSheet("color: rgba(255,255,255,0.07);")
        self.setFixedHeight(1)


class FilePickerRow(QWidget):
    """A one-line file-path input with a Browse button."""
    def __init__(self, placeholder="Select a file…", filter_str="Audio Files (*.wav *.flac *.ogg *.aiff *.aif)"):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText(placeholder)
        self.path_input.setReadOnly(True)

        self.browse_btn = QPushButton("Browse…")
        self.browse_btn.setFixedWidth(90)
        self.browse_btn.clicked.connect(self._browse)

        layout.addWidget(self.path_input)
        layout.addWidget(self.browse_btn)
        self._filter = filter_str

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Audio File", "", self._filter)
        if path:
            self.path_input.setText(path)

    def path(self) -> str:
        return self.path_input.text().strip()


class StatusBar(QWidget):
    """A slim coloured status strip shown at the bottom of a panel."""
    def __init__(self):
        super().__init__()
        self.setFixedHeight(32)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        self._label = QLabel("")
        self._label.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._label)

    def info(self, msg: str):
        self._label.setText(msg)
        self._label.setStyleSheet("font-size: 12px; color: rgba(150,220,150,1);")

    def error(self, msg: str):
        self._label.setText(f"⚠  {msg}")
        self._label.setStyleSheet("font-size: 12px; color: rgba(255,120,100,1);")

    def clear(self):
        self._label.setText("")


# ─────────────────────────────────────────────────────────────────────────────
# Encoding panel
# ─────────────────────────────────────────────────────────────────────────────

class EncodingTab(QWidget):
    def __init__(self):
        super().__init__()
        self._thread = None
        self._worker = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 20)
        root.setSpacing(16)

        # Header
        header = QLabel("Encode Watermark")
        header.setStyleSheet("font-size: 22px; font-weight: 700;")
        root.addWidget(header)

        sub = QLabel("Embed a hidden message into any audio file using ultrasonic FSK modulation.")
        sub.setWordWrap(True)
        sub.setStyleSheet("font-size: 13px; color: rgba(180,180,200,0.75);")
        root.addWidget(sub)
        root.addWidget(Divider())

        # Source file
        root.addWidget(SectionLabel("Source Audio File"))
        self.file_picker = FilePickerRow("Select the audio file to watermark…")
        root.addWidget(self.file_picker)

        # Message
        root.addWidget(SectionLabel("Message to Embed"))
        self.message = QTextEdit()
        self.message.setPlaceholderText("Enter the copyright notice or hidden message here…")
        self.message.setMinimumHeight(120)
        root.addWidget(self.message)

        # Char count
        self.char_count = QLabel("0 characters")
        self.char_count.setStyleSheet("font-size: 11px; color: rgba(150,150,170,0.7);")
        self.char_count.setAlignment(Qt.AlignRight)
        root.addWidget(self.char_count)
        self.message.textChanged.connect(self._update_char_count)

        root.addStretch()

        # Progress bar (hidden until in use)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(4)
        self.progress.hide()
        root.addWidget(self.progress)

        # Status + action button
        bottom = QHBoxLayout()
        self.status = StatusBar()
        self.export_btn = QPushButton("Export Watermarked Audio")
        self.export_btn.setFixedHeight(40)
        self.export_btn.setStyleSheet(
            "QPushButton { background: rgba(100,160,255,0.85); font-weight: 700; font-size: 14px; }"
            "QPushButton:hover { background: rgba(130,185,255,0.95); }"
            "QPushButton:disabled { background: rgba(80,80,95,0.5); color: rgba(255,255,255,0.3); }"
        )
        self.export_btn.clicked.connect(self._export)
        bottom.addWidget(self.status)
        bottom.addStretch()
        bottom.addWidget(self.export_btn)
        root.addLayout(bottom)

    def _update_char_count(self):
        n = len(self.message.toPlainText())
        self.char_count.setText(f"{n:,} character{'s' if n != 1 else ''}")

    def _export(self):
        input_file = self.file_picker.path()
        message    = self.message.toPlainText().strip()

        if not input_file:
            self.status.error("Please select a source audio file.")
            return
        if not message:
            self.status.error("Please enter a message to embed.")
            return

        settings  = load_settings()
        fmt       = settings["format"]
        chunk_ms  = settings["chunk_ms"]
        base, _   = os.path.splitext(os.path.basename(input_file))
        default   = f"{base}_watermarked.{fmt}"

        output_file, _ = QFileDialog.getSaveFileName(
            self, "Save Watermarked Audio", default,
            f"{fmt.upper()} Files (*.{fmt});;All Files (*)"
        )
        if not output_file:
            return

        self._set_busy(True)
        self.status.clear()

        self._worker = EncodeWorker(input_file, output_file, message, chunk_ms)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_encode_done)
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()

    def _on_encode_done(self, error: str):
        self._set_busy(False)
        if error:
            self.status.error(error)
        else:
            self.status.info("✓  Audio exported successfully.")

    def set_welcome(self, message: str):
        if message:
            self.message.setPlaceholderText(message)
        else:
            self.message.setPlaceholderText("Enter the copyright notice or hidden message here…")

    def _set_busy(self, busy: bool):
        self.export_btn.setEnabled(not busy)
        self.export_btn.setText("Encoding…" if busy else "Export Watermarked Audio")
        if busy:
            self.progress.show()
        else:
            self.progress.hide()


# ─────────────────────────────────────────────────────────────────────────────
# Decoding panel
# ─────────────────────────────────────────────────────────────────────────────

class DecodingTab(QWidget):
    def __init__(self):
        super().__init__()
        self._thread = None
        self._worker = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 20)
        root.setSpacing(16)

        # Header
        header = QLabel("Decode Watermark")
        header.setStyleSheet("font-size: 22px; font-weight: 700;")
        root.addWidget(header)

        sub = QLabel("Extract and reveal a hidden message from a previously watermarked audio file.")
        sub.setWordWrap(True)
        sub.setStyleSheet("font-size: 13px; color: rgba(180,180,200,0.75);")
        root.addWidget(sub)
        root.addWidget(Divider())

        # File picker
        root.addWidget(SectionLabel("Watermarked Audio File"))
        self.file_picker = FilePickerRow("Select a watermarked audio file…")
        root.addWidget(self.file_picker)

        # Result area
        root.addWidget(SectionLabel("Decoded Message"))
        self.result = QTextEdit()
        self.result.setReadOnly(True)
        self.result.setPlaceholderText("The extracted message will appear here…")
        self.result.setMinimumHeight(150)
        root.addWidget(self.result)

        # Copy button
        copy_row = QHBoxLayout()
        copy_row.addStretch()
        self.copy_btn = QPushButton("Copy to Clipboard")
        self.copy_btn.setFixedWidth(150)
        self.copy_btn.setEnabled(False)
        self.copy_btn.clicked.connect(self._copy_result)
        copy_row.addWidget(self.copy_btn)
        root.addLayout(copy_row)

        root.addStretch()

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(4)
        self.progress.hide()
        root.addWidget(self.progress)

        # Status + decode button
        bottom = QHBoxLayout()
        self.status = StatusBar()
        self.decode_btn = QPushButton("Decode Watermark")
        self.decode_btn.setFixedHeight(40)
        self.decode_btn.setStyleSheet(
            "QPushButton { background: rgba(100,200,160,0.85); font-weight: 700; font-size: 14px; color: #0d1f18; }"
            "QPushButton:hover { background: rgba(130,220,180,0.95); }"
            "QPushButton:disabled { background: rgba(80,80,95,0.5); color: rgba(255,255,255,0.3); }"
        )
        self.decode_btn.clicked.connect(self._decode)
        bottom.addWidget(self.status)
        bottom.addStretch()
        bottom.addWidget(self.decode_btn)
        root.addLayout(bottom)

    def _decode(self):
        input_file = self.file_picker.path()
        if not input_file:
            self.status.error("Please select a watermarked audio file.")
            return

        settings = load_settings()
        self.result.clear()
        self.copy_btn.setEnabled(False)
        self._set_busy(True)
        self.status.clear()

        self._worker = DecodeWorker(input_file, settings["chunk_ms"])
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_decode_done)
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()

    def _on_decode_done(self, result: str, error: str):
        self._set_busy(False)
        if error:
            self.status.error(error)
        else:
            self.result.setPlainText(result)
            self.copy_btn.setEnabled(True)
            self.status.info(f"✓  Message decoded ({len(result):,} character{'s' if len(result) != 1 else ''}).")

    def _copy_result(self):
        text = self.result.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self.status.info("✓  Copied to clipboard.")

    def set_welcome(self, message: str):
        pass  # Decode tab has no message field to update

    def _set_busy(self, busy: bool):
        self.decode_btn.setEnabled(not busy)
        self.decode_btn.setText("Decoding…" if busy else "Decode Watermark")
        if busy:
            self.progress.show()
        else:
            self.progress.hide()


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar navigation
# ─────────────────────────────────────────────────────────────────────────────

class SidebarButton(QPushButton):
    def __init__(self, text, icon_char=""):
        super().__init__(f"  {icon_char}  {text}" if icon_char else text)
        self.setCheckable(True)
        self.setFixedHeight(46)
        pass  # Styled via application stylesheet


class Sidebar(QWidget):
    tabChanged = Signal(int)

    def __init__(self):
        super().__init__()
        self.setMinimumWidth(0)
        self._expanded_width = 360
        self.setMaximumWidth(self._expanded_width)
        # Styled via application stylesheet

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 24, 12, 24)
        layout.setSpacing(4)

        brand = QLabel("AudioWizard")
        brand.setStyleSheet("font-size: 17px; font-weight: 800; letter-spacing: 0.5px; padding-left: 12px; padding-bottom: 16px;")
        layout.addWidget(brand)

        tagline = QLabel("Copyright Encoder")
        tagline.setObjectName("tagline")
        layout.addWidget(tagline)
        layout.addWidget(Divider())
        layout.addSpacing(8)

        nav_label = QLabel("NAVIGATION")
        nav_label.setObjectName("navLabel")
        layout.addWidget(nav_label)
        layout.addSpacing(4)

        self.encode_btn = SidebarButton("Encode", "⬆")
        self.decode_btn = SidebarButton("Decode", "⬇")
        self.encode_btn.setChecked(True)

        layout.addWidget(self.encode_btn)
        layout.addWidget(self.decode_btn)
        layout.addStretch()

        version = QLabel("v2.0.0")
        version.setObjectName("versionLabel")
        layout.addWidget(version)

        self.encode_btn.clicked.connect(lambda: self._switch(0))
        self.decode_btn.clicked.connect(lambda: self._switch(1))

    def _switch(self, index: int):
        self.encode_btn.setChecked(index == 0)
        self.decode_btn.setChecked(index == 1)
        self.tabChanged.emit(index)


# ─────────────────────────────────────────────────────────────────────────────
# Main window
# ─────────────────────────────────────────────────────────────────────────────

DARK_STYLESHEET = """
QWidget {
    font-family: 'Segoe UI', 'SF Pro Display', 'Helvetica Neue', sans-serif;
    font-size: 14px;
    color: #e0e0ec;
    background-color: #13131a;
}
QMainWindow, QDialog {
    background-color: #13131a;
}
QLineEdit, QTextEdit, QSpinBox, QComboBox {
    background-color: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 8px;
    padding: 7px 10px;
    color: #e0e0ec;
    selection-background-color: rgba(100,160,255,0.4);
}
QLineEdit:focus, QTextEdit:focus {
    border-color: rgba(100,160,255,0.55);
}
QPushButton {
    border: none;
    border-radius: 8px;
    padding: 7px 16px;
    background-color: rgba(80,80,100,0.55);
    color: #e0e0ec;
    font-weight: 600;
}
QPushButton:hover {
    background-color: rgba(110,110,135,0.75);
}
QPushButton:pressed {
    background-color: rgba(60,60,80,0.9);
}
QToolBar {
    background: rgba(10,10,15,0.98);
    border-bottom: 1px solid rgba(255,255,255,0.06);
    spacing: 6px;
    padding: 4px 8px;
}
QToolBar::separator {
    background: rgba(255,255,255,0.08);
    width: 1px;
    margin: 6px 4px;
}
QProgressBar {
    border: none;
    background: rgba(255,255,255,0.06);
    border-radius: 2px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(100,160,255,0.9), stop:1 rgba(160,100,255,0.9));
    border-radius: 2px;
}
QScrollBar:vertical {
    background: transparent;
    width: 8px;
}
QScrollBar::handle:vertical {
    background: rgba(255,255,255,0.15);
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView {
    background: #1e1e2a;
    border: 1px solid rgba(255,255,255,0.12);
    selection-background-color: rgba(100,160,255,0.3);
}
/* Sidebar */
Sidebar {
    background: rgba(15,15,20,0.95);
    border-right: 1px solid rgba(255,255,255,0.06);
}
SidebarButton {
    text-align: left;
    padding-left: 20px;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 600;
    color: rgba(200,200,220,0.75);
    background: transparent;
}
SidebarButton:hover {
    background: rgba(255,255,255,0.06);
    color: rgba(230,230,250,1);
}
SidebarButton:checked {
    background: rgba(100,160,255,0.18);
    color: rgba(160,200,255,1);
}
QLabel#tagline {
    font-size: 11px;
    color: rgba(150,150,180,0.6);
    letter-spacing: 1px;
    padding-left: 12px;
    padding-bottom: 20px;
}
QLabel#navLabel {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.5px;
    color: rgba(140,140,160,0.5);
    padding-left: 12px;
    padding-top: 8px;
}
QLabel#versionLabel {
    font-size: 11px;
    color: rgba(120,120,140,0.5);
    padding-left: 12px;
}
"""

LIGHT_STYLESHEET = """
QWidget {
    font-family: 'Segoe UI', 'SF Pro Display', 'Helvetica Neue', sans-serif;
    font-size: 14px;
    color: #1c1c28;
    background-color: #f0efe9;
}
QMainWindow, QDialog {
    background-color: #f0efe9;
}
QLineEdit, QTextEdit, QSpinBox, QComboBox {
    background-color: rgba(255,255,253,0.85);
    border: 1px solid rgba(0,0,0,0.10);
    border-radius: 8px;
    padding: 7px 10px;
    color: #1c1c28;
    selection-background-color: rgba(80,120,200,0.25);
}
QLineEdit:focus, QTextEdit:focus {
    border-color: rgba(80,110,190,0.55);
    background-color: #fffffd;
}
QPushButton {
    border: none;
    border-radius: 8px;
    padding: 7px 16px;
    background-color: rgba(0,0,0,0.07);
    color: #1c1c28;
    font-weight: 600;
}
QPushButton:hover {
    background-color: rgba(0,0,0,0.12);
}
QPushButton:pressed {
    background-color: rgba(0,0,0,0.18);
}
QPushButton:disabled {
    color: rgba(0,0,0,0.25);
    background-color: rgba(0,0,0,0.04);
}
QToolBar {
    background: #e8e7e0;
    border-bottom: 1px solid rgba(0,0,0,0.07);
    spacing: 6px;
    padding: 4px 8px;
}
QToolBar::separator {
    background: rgba(0,0,0,0.08);
    width: 1px;
    margin: 6px 4px;
}
QProgressBar {
    border: none;
    background: rgba(0,0,0,0.07);
    border-radius: 2px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(80,120,210,0.9), stop:1 rgba(130,80,200,0.9));
    border-radius: 2px;
}
QScrollBar:vertical {
    background: transparent;
    width: 8px;
}
QScrollBar::handle:vertical {
    background: rgba(0,0,0,0.14);
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView {
    background: #f5f4ee;
    border: 1px solid rgba(0,0,0,0.10);
    selection-background-color: rgba(80,120,210,0.15);
    color: #1c1c28;
}
/* Sidebar */
Sidebar {
    background: #e8e7e0;
    border-right: 1px solid rgba(0,0,0,0.08);
}
SidebarButton {
    text-align: left;
    padding-left: 20px;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 600;
    color: rgba(28,28,40,0.6);
    background: transparent;
}
SidebarButton:hover {
    background: rgba(0,0,0,0.06);
    color: rgba(28,28,40,0.9);
}
SidebarButton:checked {
    background: rgba(80,120,210,0.14);
    color: rgba(60,100,190,1);
}
QLabel#tagline {
    font-size: 11px;
    color: rgba(28,28,40,0.4);
    letter-spacing: 1px;
    padding-left: 12px;
    padding-bottom: 20px;
}
QLabel#navLabel {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.5px;
    color: rgba(28,28,40,0.35);
    padding-left: 12px;
    padding-top: 8px;
}
QLabel#versionLabel {
    font-size: 11px;
    color: rgba(28,28,40,0.35);
    padding-left: 12px;
}
"""


MIDNIGHT_STYLESHEET = """
QWidget {
    font-family: 'Segoe UI', 'SF Pro Display', 'Helvetica Neue', sans-serif;
    font-size: 14px;
    color: #c8d6e8;
    background-color: #0d1117;
}
QMainWindow, QDialog { background-color: #0d1117; }
QLineEdit, QTextEdit, QSpinBox, QComboBox {
    background-color: rgba(255,255,255,0.04);
    border: 1px solid rgba(100,160,255,0.15);
    border-radius: 8px;
    padding: 7px 10px;
    color: #c8d6e8;
    selection-background-color: rgba(56,139,253,0.3);
}
QLineEdit:focus, QTextEdit:focus { border-color: rgba(56,139,253,0.6); }
QPushButton {
    border: none; border-radius: 8px; padding: 7px 16px;
    background-color: rgba(56,139,253,0.12);
    color: #c8d6e8; font-weight: 600;
}
QPushButton:hover { background-color: rgba(56,139,253,0.22); }
QPushButton:pressed { background-color: rgba(56,139,253,0.35); }
QPushButton:disabled { color: rgba(200,214,232,0.25); background-color: rgba(56,139,253,0.05); }
QToolBar { background: #090d13; border-bottom: 1px solid rgba(56,139,253,0.12); spacing: 6px; padding: 4px 8px; }
QProgressBar { border: none; background: rgba(56,139,253,0.08); border-radius: 2px; }
QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #388bfd, stop:1 #58a6ff); border-radius: 2px; }
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: rgba(56,139,253,0.25); border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView { background: #161b22; border: 1px solid rgba(56,139,253,0.2); selection-background-color: rgba(56,139,253,0.2); color: #c8d6e8; }
Sidebar { background: #090d13; border-right: 1px solid rgba(56,139,253,0.12); }
SidebarButton { text-align: left; padding-left: 20px; border: none; border-radius: 8px; font-size: 14px; font-weight: 600; color: rgba(200,214,232,0.6); background: transparent; }
SidebarButton:hover { background: rgba(56,139,253,0.1); color: rgba(200,214,232,0.9); }
SidebarButton:checked { background: rgba(56,139,253,0.2); color: #58a6ff; }
QLabel#tagline { font-size: 11px; color: rgba(200,214,232,0.35); letter-spacing: 1px; padding-left: 12px; padding-bottom: 20px; }
QLabel#navLabel { font-size: 10px; font-weight: 700; letter-spacing: 1.5px; color: rgba(200,214,232,0.3); padding-left: 12px; padding-top: 8px; }
QLabel#versionLabel { font-size: 11px; color: rgba(200,214,232,0.3); padding-left: 12px; }
"""

OCEAN_STYLESHEET = """
QWidget {
    font-family: 'Segoe UI', 'SF Pro Display', 'Helvetica Neue', sans-serif;
    font-size: 14px;
    color: #e0f0f0;
    background-color: #0a1628;
}
QMainWindow, QDialog { background-color: #0a1628; }
QLineEdit, QTextEdit, QSpinBox, QComboBox {
    background-color: rgba(0,200,180,0.06);
    border: 1px solid rgba(0,200,180,0.18);
    border-radius: 8px; padding: 7px 10px; color: #e0f0f0;
    selection-background-color: rgba(0,200,180,0.25);
}
QLineEdit:focus, QTextEdit:focus { border-color: rgba(0,200,180,0.55); }
QPushButton {
    border: none; border-radius: 8px; padding: 7px 16px;
    background-color: rgba(0,200,180,0.12); color: #e0f0f0; font-weight: 600;
}
QPushButton:hover { background-color: rgba(0,200,180,0.22); }
QPushButton:pressed { background-color: rgba(0,200,180,0.35); }
QPushButton:disabled { color: rgba(224,240,240,0.25); background-color: rgba(0,200,180,0.05); }
QToolBar { background: #071020; border-bottom: 1px solid rgba(0,200,180,0.12); spacing: 6px; padding: 4px 8px; }
QProgressBar { border: none; background: rgba(0,200,180,0.08); border-radius: 2px; }
QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #00c8b4, stop:1 #0099cc); border-radius: 2px; }
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: rgba(0,200,180,0.25); border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView { background: #0d1f38; border: 1px solid rgba(0,200,180,0.2); selection-background-color: rgba(0,200,180,0.18); color: #e0f0f0; }
Sidebar { background: #071020; border-right: 1px solid rgba(0,200,180,0.12); }
SidebarButton { text-align: left; padding-left: 20px; border: none; border-radius: 8px; font-size: 14px; font-weight: 600; color: rgba(224,240,240,0.6); background: transparent; }
SidebarButton:hover { background: rgba(0,200,180,0.1); color: rgba(224,240,240,0.9); }
SidebarButton:checked { background: rgba(0,200,180,0.18); color: #00c8b4; }
QLabel#tagline { font-size: 11px; color: rgba(224,240,240,0.35); letter-spacing: 1px; padding-left: 12px; padding-bottom: 20px; }
QLabel#navLabel { font-size: 10px; font-weight: 700; letter-spacing: 1.5px; color: rgba(224,240,240,0.3); padding-left: 12px; padding-top: 8px; }
QLabel#versionLabel { font-size: 11px; color: rgba(224,240,240,0.3); padding-left: 12px; }
"""

ROSE_STYLESHEET = """
QWidget {
    font-family: 'Segoe UI', 'SF Pro Display', 'Helvetica Neue', sans-serif;
    font-size: 14px;
    color: #2d1f26;
    background-color: #fdf6f8;
}
QMainWindow, QDialog { background-color: #fdf6f8; }
QLineEdit, QTextEdit, QSpinBox, QComboBox {
    background-color: rgba(255,255,255,0.9);
    border: 1px solid rgba(200,100,130,0.18);
    border-radius: 8px; padding: 7px 10px; color: #2d1f26;
    selection-background-color: rgba(200,100,130,0.2);
}
QLineEdit:focus, QTextEdit:focus { border-color: rgba(200,100,130,0.5); }
QPushButton {
    border: none; border-radius: 8px; padding: 7px 16px;
    background-color: rgba(200,100,130,0.1); color: #2d1f26; font-weight: 600;
}
QPushButton:hover { background-color: rgba(200,100,130,0.18); }
QPushButton:pressed { background-color: rgba(200,100,130,0.28); }
QPushButton:disabled { color: rgba(45,31,38,0.25); background-color: rgba(200,100,130,0.05); }
QToolBar { background: #f5eaee; border-bottom: 1px solid rgba(200,100,130,0.12); spacing: 6px; padding: 4px 8px; }
QProgressBar { border: none; background: rgba(200,100,130,0.08); border-radius: 2px; }
QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #e06080, stop:1 #c84070); border-radius: 2px; }
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: rgba(200,100,130,0.2); border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView { background: #fdf0f3; border: 1px solid rgba(200,100,130,0.15); selection-background-color: rgba(200,100,130,0.12); color: #2d1f26; }
Sidebar { background: #f5eaee; border-right: 1px solid rgba(200,100,130,0.12); }
SidebarButton { text-align: left; padding-left: 20px; border: none; border-radius: 8px; font-size: 14px; font-weight: 600; color: rgba(45,31,38,0.55); background: transparent; }
SidebarButton:hover { background: rgba(200,100,130,0.08); color: rgba(45,31,38,0.85); }
SidebarButton:checked { background: rgba(200,100,130,0.15); color: #c84070; }
QLabel#tagline { font-size: 11px; color: rgba(45,31,38,0.38); letter-spacing: 1px; padding-left: 12px; padding-bottom: 20px; }
QLabel#navLabel { font-size: 10px; font-weight: 700; letter-spacing: 1.5px; color: rgba(45,31,38,0.32); padding-left: 12px; padding-top: 8px; }
QLabel#versionLabel { font-size: 11px; color: rgba(45,31,38,0.32); padding-left: 12px; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AudioWizard — Copyright Encoder")
        self.resize(1200, 780)
        self.setMinimumSize(1000, 660)

        # ── Central layout ────────────────────────────────────────────────
        container = QWidget()
        self.setCentralWidget(container)
        h_layout = QHBoxLayout(container)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(0)

        self.sidebar = Sidebar()
        self.stack   = QStackedWidget()
        self.encode_tab = EncodingTab()
        self.decode_tab = DecodingTab()
        self.stack.addWidget(self.encode_tab)
        self.stack.addWidget(self.decode_tab)

        h_layout.addWidget(self.sidebar)
        h_layout.addWidget(self.stack)

        self.sidebar.tabChanged.connect(self.stack.setCurrentIndex)
        self._sidebar_visible = False
        self.sidebar.setMaximumWidth(0)

        # ── Toolbar ───────────────────────────────────────────────────────
        self._create_toolbar()

        # ── App icon ──────────────────────────────────────────────────────
        self.setWindowIcon(QIcon("icons/icon.png"))

        # ── Apply saved theme + welcome message ───────────────────────────
        settings = load_settings()
        self._apply_theme(settings["theme"])
        self._apply_welcome(settings.get("welcome", ""))

    def _create_toolbar(self):
        from PySide6.QtCore import QSize
        toolbar = QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        btn_style = (
            "QPushButton {"
            "  background: transparent;"
            "  border: none;"
            "  border-radius: 8px;"
            "  padding: 5px;"
            "  margin: 2px;"
            "}"
            "QPushButton:hover {"
            "  background: rgba(128,128,128,0.15);"
            "}"
            "QPushButton:pressed {"
            "  background: rgba(128,128,128,0.32);"
            "}"
        )

        self._menu_btn = QPushButton()
        self._menu_btn.setIcon(QIcon("icons/hamburger.png"))
        self._menu_btn.setIconSize(QSize(20, 20))
        self._menu_btn.setFixedSize(36, 36)
        self._menu_btn.setStyleSheet(btn_style)
        self._menu_btn.setToolTip("Toggle Sidebar")
        self._menu_btn.clicked.connect(self._toggle_sidebar)
        toolbar.addWidget(self._menu_btn)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        self._settings_btn = QPushButton()
        self._settings_btn.setIcon(QIcon("icons/settings.png"))
        self._settings_btn.setIconSize(QSize(20, 20))
        self._settings_btn.setFixedSize(36, 36)
        self._settings_btn.setStyleSheet(btn_style)
        self._settings_btn.setToolTip("Settings")
        self._settings_btn.clicked.connect(self._open_settings)
        toolbar.addWidget(self._settings_btn)

    def _toggle_sidebar(self):
        from PySide6.QtCore import QParallelAnimationGroup
        start, end = (self.sidebar.maximumWidth(), 0) if self._sidebar_visible else (0, self.sidebar._expanded_width)
        self._anim_group = QParallelAnimationGroup()
        for prop in (b"minimumWidth", b"maximumWidth"):
            a = QPropertyAnimation(self.sidebar, prop)
            a.setDuration(220)
            a.setEasingCurve(QEasingCurve.InOutCubic)
            a.setStartValue(start)
            a.setEndValue(end)
            self._anim_group.addAnimation(a)
        self._sidebar_visible = not self._sidebar_visible
        self._anim_group.start()

    def _open_settings(self):
        dlg = SettingsWindow(self)
        if dlg.exec() == QDialog.Accepted:
            settings = load_settings()
            self._apply_theme(settings["theme"])
            self._apply_welcome(settings.get("welcome", ""))

    def _apply_welcome(self, message: str):
        self.encode_tab.set_welcome(message)
        self.decode_tab.set_welcome(message)

    def _apply_theme(self, theme: str):
        themes = {
            "Dark":        DARK_STYLESHEET,
            "Light":       LIGHT_STYLESHEET,
            "Midnight":    MIDNIGHT_STYLESHEET,
            "Ocean":       OCEAN_STYLESHEET,
            "Rose":        ROSE_STYLESHEET,
        }
        QApplication.instance().setStyleSheet(themes.get(theme, DARK_STYLESHEET))
        self._update_toolbar_icons(theme)

    def _update_toolbar_icons(self, theme: str):
        from PySide6.QtCore import QSize
        dark_themes = {"Dark", "Midnight", "Ocean"}
        if theme in dark_themes:
            self._menu_btn.setIcon(QIcon("icons/dark_hamburger.png"))
            self._settings_btn.setIcon(QIcon("icons/dark_settings.png"))
        else:
            self._menu_btn.setIcon(QIcon("icons/hamburger.png"))
            self._settings_btn.setIcon(QIcon("icons/settings.png"))


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Required on macOS for PySide6 to display a window
    os.environ.setdefault("QT_MAC_WANTS_LAYER", "1")

    # Ensure assets can be found regardless of working directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    app = QApplication(sys.argv)
    app.setApplicationDisplayName("AudioWizard")
    app.setApplicationName("AudioWizard")
    app.setOrganizationName("AudioWizard")
    app.setWindowIcon(QIcon("icons/icon.png"))
    app.setWindowIcon(QIcon("icons/icon.png").pixmap(QSize(128, 128)))

    window = MainWindow()
    window.show()
    sys.exit(app.exec())