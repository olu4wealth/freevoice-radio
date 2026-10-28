"""Settings dialog for Freevoice Radio.

Provides a comprehensive preferences window for all togglable features.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QPushButton, QComboBox, QCheckBox, QSlider,
    QFileDialog, QDialogButtonBox, QGroupBox, QSpinBox, QLineEdit,
)
from PyQt6.QtCore import Qt

from src.config import Config


class SettingsDialog(QDialog):
    def __init__(self, config: Config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Settings — Freevoice Radio")
        self.setModal(True)
        self.resize(520, 480)
        self._build_ui()
        self._load_from_config()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._playback_tab(), "Playback")
        tabs.addTab(self._youtube_tab(), "YouTube")
        tabs.addTab(self._general_tab(), "General")
        layout.addWidget(tabs)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _playback_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        grp = QGroupBox("Loop Mode")
        gv = QVBoxLayout(grp)
        self.loop_combo = QComboBox()
        self.loop_combo.addItems(["Loop All", "Loop One", "Off"])
        gv.addWidget(QLabel("Playlist behavior:"))
        gv.addWidget(self.loop_combo)
        v.addWidget(grp)

        self.shuffle_chk = QCheckBox("Shuffle playback order")
        v.addWidget(self.shuffle_chk)

        self.gapless_chk = QCheckBox("Gapless playback (no gap between tracks)")
        v.addWidget(self.gapless_chk)

        cf_grp = QGroupBox("Crossfade")
        cf_v = QVBoxLayout(cf_grp)
        self.crossfade_chk = QCheckBox("Enable crossfade between tracks")
        cf_v.addWidget(self.crossfade_chk)
        cf_h = QHBoxLayout()
        cf_h.addWidget(QLabel("Duration (seconds):"))
        self.crossfade_spin = QSpinBox()
        self.crossfade_spin.setRange(1, 30)
        self.crossfade_spin.setValue(5)
        cf_h.addWidget(self.crossfade_spin)
        cf_h.addStretch()
        cf_v.addLayout(cf_h)
        v.addWidget(cf_grp)

        sil_grp = QGroupBox("Silence Between Tracks")
        sil_v = QVBoxLayout(sil_grp)
        self.silence_chk = QCheckBox("Insert silence between tracks")
        sil_v.addWidget(self.silence_chk)
        sil_h = QHBoxLayout()
        sil_h.addWidget(QLabel("Duration (seconds):"))
        self.silence_spin = QSpinBox()
        self.silence_spin.setRange(1, 10)
        self.silence_spin.setValue(2)
        sil_h.addWidget(self.silence_spin)
        sil_h.addStretch()
        sil_v.addLayout(sil_h)
        v.addWidget(sil_grp)

        vol_h = QHBoxLayout()
        vol_h.addWidget(QLabel("Volume:"))
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        vol_h.addWidget(self.volume_slider)
        v.addLayout(vol_h)

        v.addStretch()
        return w

    def _youtube_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        yt_grp = QGroupBox("YouTube Audio Mode")
        yt_v = QVBoxLayout(yt_grp)
        self.youtube_mode_combo = QComboBox()
        self.youtube_mode_combo.addItems(["Download (save to disk)", "Stream (temp file)"])
        yt_v.addWidget(QLabel("How to handle YouTube audio:"))
        yt_v.addWidget(self.youtube_mode_combo)
        v.addWidget(yt_grp)

        fmt_grp = QGroupBox("Audio Format")
        fmt_v = QVBoxLayout(fmt_grp)
        self.format_combo = QComboBox()
        self.format_combo.addItems(["mp3", "wav", "flac", "m4a"])
        fmt_v.addWidget(QLabel("Format for downloaded/converted audio:"))
        fmt_v.addWidget(self.format_combo)
        v.addWidget(fmt_grp)

        qual_grp = QGroupBox("MP3 Quality")
        qual_v = QVBoxLayout(qual_grp)
        qual_h = QHBoxLayout()
        qual_h.addWidget(QLabel("Bitrate (kbps):"))
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["96", "128", "160", "192", "256", "320"])
        qual_h.addWidget(self.quality_combo)
        qual_h.addStretch()
        qual_v.addLayout(qual_h)
        qual_hint = QLabel(
            "Lower bitrate = smaller files. Roughly: 128 kbps ≈ 58 MB/hour, "
            "192 kbps ≈ 86 MB/hour. Only used when converting to MP3."
        )
        qual_hint.setWordWrap(True)
        qual_v.addWidget(qual_hint)
        v.addWidget(qual_grp)

        path_h = QHBoxLayout()
        path_h.addWidget(QLabel("Download folder:"))
        self.download_path_edit = QLineEdit(self.config.download_path)
        self.download_path_edit.setReadOnly(True)
        path_h.addWidget(self.download_path_edit, stretch=1)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_download_path)
        path_h.addWidget(browse_btn)
        v.addLayout(path_h)

        hint = QLabel(
            "yt-dlp needs ffmpeg to extract audio. Keep ffmpeg.exe next to the "
            "app (or on PATH)."
        )
        hint.setWordWrap(True)
        v.addWidget(hint)

        v.addStretch()
        return w

    def _general_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)

        theme_h = QHBoxLayout()
        theme_h.addWidget(QLabel("Theme:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark", "Light", "System"])
        theme_h.addWidget(self.theme_combo)
        theme_h.addStretch()
        v.addLayout(theme_h)

        self.autoplay_chk = QCheckBox("Start playing when Freevoice Radio opens")
        v.addWidget(self.autoplay_chk)

        close_h = QHBoxLayout()
        close_h.addWidget(QLabel("When I click the close button:"))
        self.close_combo = QComboBox()
        self.close_combo.addItems(
            ["Ask every time", "Minimize to tray and keep playing", "Close the app"]
        )
        close_h.addWidget(self.close_combo)
        close_h.addStretch()
        v.addLayout(close_h)

        sched_grp = QGroupBox("Channel Auto-Update")
        sched_v = QVBoxLayout(sched_grp)
        self.sched_chk = QCheckBox("Enable automatic channel polling")
        sched_v.addWidget(self.sched_chk)
        sched_h = QHBoxLayout()
        sched_h.addWidget(QLabel("Check every (minutes):"))
        self.sched_spin = QSpinBox()
        self.sched_spin.setRange(5, 1440)
        self.sched_spin.setValue(60)
        sched_h.addWidget(self.sched_spin)
        sched_h.addStretch()
        sched_v.addLayout(sched_h)
        v.addWidget(sched_grp)

        v.addStretch()
        return w

    def _load_from_config(self) -> None:
        cfg = self.config
        loop_map = {"loop_all": 0, "loop_one": 1, "off": 2}
        self.loop_combo.setCurrentIndex(loop_map.get(cfg.loop_mode, 0))
        self.shuffle_chk.setChecked(cfg.shuffle)
        self.gapless_chk.setChecked(cfg.gapless)
        self.crossfade_chk.setChecked(cfg.crossfade_enabled)
        self.crossfade_spin.setValue(cfg.crossfade_seconds)
        self.silence_chk.setChecked(cfg.silence_between_tracks)
        self.silence_spin.setValue(cfg.silence_seconds)
        self.volume_slider.setValue(cfg.volume)
        yt_map = {"download": 0, "stream": 1}
        self.youtube_mode_combo.setCurrentIndex(yt_map.get(cfg.youtube_mode, 0))
        self.format_combo.setCurrentText(cfg.audio_format)
        self.quality_combo.setCurrentText(cfg.audio_quality)
        self.download_path_edit.setText(cfg.download_path or "")
        theme_map = {"dark": 0, "light": 1, "system": 2}
        self.theme_combo.setCurrentIndex(theme_map.get(cfg.theme, 0))
        self.autoplay_chk.setChecked(cfg.autoplay)
        close_map = {"ask": 0, "tray": 1, "quit": 2}
        self.close_combo.setCurrentIndex(close_map.get(cfg.close_action, 0))
        self.sched_chk.setChecked(cfg.scheduler_enabled)
        self.sched_spin.setValue(cfg.scheduler_interval_minutes)

    def _on_accept(self) -> None:
        cfg = self.config
        loop_map = {0: "loop_all", 1: "loop_one", 2: "off"}
        cfg.loop_mode = loop_map[self.loop_combo.currentIndex()]
        cfg.shuffle = self.shuffle_chk.isChecked()
        cfg.gapless = self.gapless_chk.isChecked()
        cfg.crossfade_enabled = self.crossfade_chk.isChecked()
        cfg.crossfade_seconds = self.crossfade_spin.value()
        cfg.silence_between_tracks = self.silence_chk.isChecked()
        cfg.silence_seconds = self.silence_spin.value()
        cfg.volume = self.volume_slider.value()
        yt_map = {0: "download", 1: "stream"}
        cfg.youtube_mode = yt_map[self.youtube_mode_combo.currentIndex()]
        cfg.audio_format = self.format_combo.currentText()
        cfg.audio_quality = self.quality_combo.currentText()
        cfg.download_path = self.download_path_edit.text() or "downloads"
        theme_map = {0: "dark", 1: "light", 2: "system"}
        cfg.theme = theme_map[self.theme_combo.currentIndex()]
        cfg.autoplay = self.autoplay_chk.isChecked()
        close_map = {0: "ask", 1: "tray", 2: "quit"}
        cfg.close_action = close_map[self.close_combo.currentIndex()]
        cfg.scheduler_enabled = self.sched_chk.isChecked()
        cfg.scheduler_interval_minutes = self.sched_spin.value()
        cfg.save()
        self.accept()

    def _browse_download_path(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Download Folder")
        if folder:
            self.download_path_edit.setText(folder)