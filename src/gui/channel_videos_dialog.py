"""Pick which videos from a YouTube channel to download."""

from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from src.youtube.channel_scraper import ChannelVideo


def _format_duration(seconds: int) -> str:
    if not seconds:
        return "—"
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _format_date(value: Optional[str]) -> str:
    if not value or len(str(value)) != 8:
        return "—"
    text = str(value)
    return f"{text[:4]}-{text[4:6]}-{text[6:]}"


class ChannelVideosDialog(QDialog):
    """Checkbox list of a channel's latest videos."""

    def __init__(
        self,
        parent=None,
        channel_name: str = "",
        videos: Optional[list[ChannelVideo]] = None,
        is_downloaded: Optional[Callable[[ChannelVideo], bool]] = None,
    ) -> None:
        super().__init__(parent)
        self._videos = videos or []
        self._is_downloaded = is_downloaded or (lambda video: False)
        self._loading = True
        self.setWindowTitle(f"Select Videos — {channel_name}" if channel_name else "Select Videos")
        self.resize(820, 500)
        self._build_ui()
        self._populate()
        self._loading = False
        self._update_selection()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        label = QLabel(
            "Choose the videos to add to the download queue. "
            "Videos already in the library are disabled."
        )
        label.setWordWrap(True)
        layout.addWidget(label)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["", "Title", "Duration", "Published", "Status"]
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 36)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemChanged.connect(self._update_selection)
        layout.addWidget(self.table, stretch=1)

        row = QHBoxLayout()
        self.btn_all = QPushButton("Select All")
        self.btn_all.clicked.connect(self._select_all)
        self.btn_none = QPushButton("Select None")
        self.btn_none.clicked.connect(self._select_none)
        row.addWidget(self.btn_all)
        row.addWidget(self.btn_none)
        row.addStretch()

        self.count_label = QLabel("")
        row.addWidget(self.count_label)

        self.btn_download = QPushButton("Download Selected")
        self.btn_download.setObjectName("playButton")
        self.btn_download.clicked.connect(self.accept)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        row.addWidget(self.btn_download)
        row.addWidget(self.btn_cancel)
        layout.addLayout(row)

    def _populate(self) -> None:
        self.table.setRowCount(len(self._videos))
        for row, video in enumerate(self._videos):
            downloaded = self._is_downloaded(video)

            check = QTableWidgetItem()
            check.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                if downloaded
                else (
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsUserCheckable
                )
            )
            check.setCheckState(
                Qt.CheckState.Unchecked
                if downloaded
                else Qt.CheckState.Checked
            )
            check.setToolTip(
                "Already in the library" if downloaded else "Queue this video"
            )
            self.table.setItem(row, 0, check)

            title = QTableWidgetItem(video.title or video.id)
            title.setToolTip(video.url)
            self.table.setItem(row, 1, title)
            self.table.setItem(
                row, 2, QTableWidgetItem(_format_duration(video.duration))
            )
            self.table.setItem(
                row, 3, QTableWidgetItem(_format_date(video.upload_date))
            )
            status = QTableWidgetItem(
                "Already downloaded" if downloaded else "New"
            )
            self.table.setItem(row, 4, status)

    # ------------------------------------------------------------------
    def _select_all(self) -> None:
        self._loading = True
        for row, video in enumerate(self._videos):
            if self._is_downloaded(video):
                continue
            self.table.item(row, 0).setCheckState(Qt.CheckState.Checked)
        self._loading = False
        self._update_selection()

    def _select_none(self) -> None:
        self._loading = True
        for row, video in enumerate(self._videos):
            if self._is_downloaded(video):
                continue
            self.table.item(row, 0).setCheckState(Qt.CheckState.Unchecked)
        self._loading = False
        self._update_selection()

    def _update_selection(self, *_args) -> None:
        if self._loading:
            return
        count = len(self.selected_videos())
        self.count_label.setText(f"{count} selected")
        self.btn_download.setEnabled(count > 0)

    def selected_videos(self) -> list[ChannelVideo]:
        selected: list[ChannelVideo] = []
        for row, video in enumerate(self._videos):
            item = self.table.item(row, 0)
            if item is None:
                continue
            if item.checkState() == Qt.CheckState.Checked and not self._is_downloaded(
                video
            ):
                selected.append(video)
        return selected
