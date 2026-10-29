"""Channel manager dialog for Freevoice Radio."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from src.config import Config
from src.youtube.channel_scraper import video_id_from_url


class ChannelsDialog(QDialog):
    """List, enable, remove and fetch configured YouTube channels."""

    def __init__(self, config: Config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.fetch_url: Optional[str] = None
        self.video_url: Optional[str] = None
        self.live_url: Optional[str] = None
        self._loading = False
        self._saving = False
        self.setWindowTitle("Manage YouTube Channels")
        self.resize(720, 420)
        self._build_ui()
        self._reload()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        hint = QLabel(
            "Auto-download is off by default. Tick it only for channels whose "
            "new videos should download automatically. Browse Videos… fetches "
            "the latest list so you can choose manually; Play Live opens the "
            "channel's live broadcast."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Auto-download", "Channel URL", "Last checked", "Videos"]
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table, stretch=1)

        buttons = QHBoxLayout()
        add_btn = QPushButton("Add Channel…")
        add_btn.clicked.connect(self._add_channel)
        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self._remove_selected)
        fetch_btn = QPushButton("Browse Videos…")
        fetch_btn.clicked.connect(self._fetch_now)
        live_btn = QPushButton("Play Live")
        live_btn.clicked.connect(self._play_live)
        buttons.addWidget(add_btn)
        buttons.addWidget(remove_btn)
        buttons.addWidget(fetch_btn)
        buttons.addWidget(live_btn)
        buttons.addStretch()
        layout.addLayout(buttons)

        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self._close)
        layout.addWidget(box)

    # ------------------------------------------------------------------
    def _reload(self) -> None:
        self._loading = True
        channels = self.config.channels
        self.table.setRowCount(len(channels))
        for row, channel in enumerate(channels):
            enabled = QTableWidgetItem()
            enabled.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
            )
            enabled.setCheckState(
                Qt.CheckState.Checked
                if channel.get("auto_download", False)
                else Qt.CheckState.Unchecked
            )
            self.table.setItem(row, 0, enabled)

            url_item = QTableWidgetItem(channel.get("url") or channel.get("id") or "")
            url_item.setData(Qt.ItemDataRole.UserRole, channel.get("url"))
            self.table.setItem(row, 1, url_item)

            self.table.setItem(
                row, 2, QTableWidgetItem(self._format_checked(channel.get("last_checked")))
            )

            spin = QSpinBox()
            spin.setRange(1, 50)
            spin.setValue(int(channel.get("max_videos_per_fetch") or 10))
            self.table.setCellWidget(row, 3, spin)

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self._loading = False

    @staticmethod
    def _format_checked(value) -> str:
        if not value:
            return "Never"
        try:
            parsed = datetime.strptime(str(value), "%Y%m%d%H%M%S")
            return parsed.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return str(value)

    # ------------------------------------------------------------------
    def _save(self) -> None:
        if self._saving:
            return
        self._saving = True
        try:
            channels = self.config.channels
            for row, channel in enumerate(channels):
                auto_item = self.table.item(row, 0)
                spin = self.table.cellWidget(row, 3)
                if auto_item is not None:
                    wanted = (
                        auto_item.checkState() == Qt.CheckState.Checked
                    )
                    if wanted and not channel.get("auto_download", False):
                        answer = QMessageBox.question(
                            self,
                            "Automatic downloads",
                            "Download new videos from this channel "
                            "automatically?\n\nThis uses network and disk space "
                            "without asking again.",
                            QMessageBox.StandardButton.Yes
                            | QMessageBox.StandardButton.No,
                            QMessageBox.StandardButton.No,
                        )
                        if answer != QMessageBox.StandardButton.Yes:
                            wanted = False
                            self._loading = True
                            auto_item.setCheckState(Qt.CheckState.Unchecked)
                            self._loading = False
                    channel["auto_download"] = wanted
                    channel["enabled"] = wanted
                if isinstance(spin, QSpinBox):
                    channel["max_videos_per_fetch"] = spin.value()
            self.config.save()
        finally:
            self._saving = False

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading or self._saving:
            return
        if item.column() == 0:
            self._save()

    def _close(self) -> None:
        self._save()
        self.reject()

    def _add_channel(self) -> None:
        url, ok = QInputDialog.getText(
            self, "Add YouTube Channel", "Channel URL:"
        )
        if not ok or not url.strip():
            return
        url = url.strip()
        if video_id_from_url(url):
            # A single video is not a channel; hand it back to the main window.
            self._save()
            self.video_url = url
            self.accept()
            return
        if any((c.get("url") or "") == url for c in self.config.channels):
            QMessageBox.information(self, "Channel", "That channel is already in the list.")
            return
        self.config.add_channel(
            {
                "id": url,
                "name": url,
                "url": url,
                "enabled": False,
                "auto_download": False,
                "last_checked": None,
                "max_videos_per_fetch": 10,
            }
        )
        self.config.save()
        self._reload()

    def _remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        if not rows:
            return
        urls = [
            self.table.item(row, 1).data(Qt.ItemDataRole.UserRole)
            for row in rows
            if self.table.item(row, 1)
        ]
        for url in urls:
            if url:
                self.config.remove_channel(url)
        self.config.save()
        self._reload()

    def _fetch_now(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        if not rows:
            QMessageBox.information(self, "Channel", "Select a channel first.")
            return
        row = rows[0]
        url = self.table.item(row, 1).data(Qt.ItemDataRole.UserRole)
        if not url:
            return
        self._save()
        self.fetch_url = url
        self.accept()

    def _play_live(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        if not rows:
            QMessageBox.information(self, "Channel", "Select a channel first.")
            return
        row = rows[0]
        url = self.table.item(row, 1).data(Qt.ItemDataRole.UserRole)
        if not url:
            return
        self._save()
        self.live_url = url
        self.accept()

    # ------------------------------------------------------------------
    def accept(self) -> None:
        self._save()
        super().accept()

    def reject(self) -> None:
        self._save()
        super().reject()
