from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QSpinBox, QPushButton, QFrame, QWidget, QLineEdit,
)
from PySide6.QtCore import Qt, QSettings

APP_ORG = "AudioWizard"
APP_NAME = "CopyrightEncoder"


def load_settings() -> dict:
    """Load persisted application settings."""
    s = QSettings(APP_ORG, APP_NAME)
    return {
        "theme":    s.value("theme",    "Dark"),
        "chunk_ms": int(s.value("chunk_ms", 50)),
        "format":   s.value("format",   "wav"),
        "welcome":  s.value("welcome",  ""),
    }


def save_settings(theme: str, chunk_ms: int, fmt: str, welcome: str) -> None:
    """Persist application settings."""
    s = QSettings(APP_ORG, APP_NAME)
    s.setValue("theme",    theme)
    s.setValue("chunk_ms", chunk_ms)
    s.setValue("format",   fmt)
    s.setValue("welcome",  welcome)


class Divider(QFrame):
    def __init__(self):
        super().__init__()
        self.setFrameShape(QFrame.HLine)
        self.setFrameShadow(QFrame.Sunken)
        self.setStyleSheet("color: rgba(255,255,255,0.1);")


class SectionLabel(QLabel):
    def __init__(self, text):
        super().__init__(text)
        self.setStyleSheet(
            "font-size: 11px; font-weight: 700; letter-spacing: 1.5px;"
            "color: rgba(180,180,200,0.8);"
        )


class SettingsRow(QWidget):
    """A labelled row for a settings control."""
    def __init__(self, label: str, widget: QWidget):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label)
        lbl.setMinimumWidth(180)
        layout.addWidget(lbl)
        layout.addWidget(widget)


class SettingsWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings — AudioWizard")
        self.setFixedSize(520, 440)
        self.setWindowModality(Qt.ApplicationModal)

        current = load_settings()

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(32, 28, 32, 24)

        # ── Title ────────────────────────────────────────────────────────────
        title = QLabel("Preferences")
        title.setStyleSheet("font-size: 18px; font-weight: 700; letter-spacing: 1px;")
        layout.addWidget(title)
        layout.addWidget(Divider())

        # ── Theme ────────────────────────────────────────────────────────────
        self.themeCombo = QComboBox()
        self.themeCombo.addItems(["Dark", "Light", "Midnight", "Ocean", "Rose"])
        self.themeCombo.setCurrentText(current["theme"])
        layout.addWidget(SettingsRow("Interface Theme", self.themeCombo))

        # ── Chunk size ───────────────────────────────────────────────────────
        self.chunkSpin = QSpinBox()
        self.chunkSpin.setRange(10, 500)
        self.chunkSpin.setSingleStep(10)
        self.chunkSpin.setSuffix(" ms")
        self.chunkSpin.setValue(current["chunk_ms"])
        self.chunkSpin.setToolTip(
            "Duration of each encoded bit tone.\n"
            "Larger values are more robust but reduce capacity.\n"
            "Must match on both encode and decode."
        )
        layout.addWidget(SettingsRow("Bit Duration (chunk size)", self.chunkSpin))

        # ── Output format ────────────────────────────────────────────────────
        self.formatCombo = QComboBox()
        self.formatCombo.addItems(["wav", "flac", "ogg"])
        self.formatCombo.setCurrentText(current["format"])
        self.formatCombo.setToolTip(
            "Default output format for encoded audio.\n"
            "WAV is lossless and recommended. OGG/FLAC may degrade the watermark."
        )
        layout.addWidget(SettingsRow("Default Output Format", self.formatCombo))

        # ── Welcome message ──────────────────────────────────────────────────
        layout.addWidget(SectionLabel("Custom Placeholder Message"))
        self.welcomeEdit = QLineEdit()
        self.welcomeEdit.setPlaceholderText("Leave blank to use the default message…")
        self.welcomeEdit.setText(current.get("welcome", ""))
        self.welcomeEdit.setToolTip(
            "This text will appear as the placeholder in the encode message box."
        )
        layout.addWidget(self.welcomeEdit)

        layout.addWidget(Divider())
        layout.addStretch()

        # ── Buttons ──────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        ok_btn = QPushButton("Save")
        ok_btn.setDefault(True)
        cancel_btn.setFixedWidth(100)
        ok_btn.setFixedWidth(100)
        ok_btn.setStyleSheet(
            "QPushButton { background-color: rgba(100,160,255,0.85); font-weight: 700; }"
            "QPushButton:hover { background-color: rgba(130,180,255,0.95); }"
        )
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

        cancel_btn.clicked.connect(self.reject)
        ok_btn.clicked.connect(self._accept)

    def _accept(self):
        save_settings(
            self.themeCombo.currentText(),
            self.chunkSpin.value(),
            self.formatCombo.currentText(),
            self.welcomeEdit.text().strip(),
        )
        self.accept()