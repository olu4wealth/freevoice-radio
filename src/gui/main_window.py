"""Main window for Freevoice Radio."""

from __future__ import annotations

import os
import time
import traceback
from typing import Optional

from PyQt6.QtCore import QPoint, QSize, Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import (
    QAction,
    QColor,
    QGuiApplication,
    QIcon,
    QKeySequence,
    QPainter,
    QPalette,
    QPixmap,
    QPolygon,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDockWidget,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QStyle,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.app_paths import resolve_path
from src.audio.engine import AUDIO_EXTENSIONS, AudioEngine
from src.config import Config
from src.scheduler.updater import ChannelUpdater
from src.youtube.channel_scraper import ChannelScraper, video_id_from_url
from src.youtube.download_queue import DownloadQueue
from src.youtube.downloader import YouTubeDownloader, YouTubeTrack

# Colours substituted into src/gui/themes.qss (@token -> value).
THEME_COLORS = {
    "dark": {
        "bg": "#1a1a1a",
        "panel": "#2a2a2a",
        "panel_alt": "#333333",
        "border": "#3d3d3d",
        "border_strong": "#555555",
        "text": "#e0e0e0",
        "text_strong": "#ffffff",
        "text_muted": "#b0b0b0",
        "text_dim": "#888888",
        "button": "#3d3d3d",
        "button_hover": "#4d4d4d",
        "button_pressed": "#2d2d2d",
        "button_border": "#555555",
        "accent": "#007acc",
        "accent_hover": "#008aec",
        "accent_pressed": "#005a9e",
        "accent_text": "#ffffff",
        "selection": "#007acc",
        "selection_text": "#ffffff",
        "onair": "#ff5252",
        "scrollbar": "#4a4a4a",
        "scrollbar_hover": "#5a5a5a",
    },
    "light": {
        "bg": "#f5f5f5",
        "panel": "#ffffff",
        "panel_alt": "#eeeeee",
        "border": "#d8d8d8",
        "border_strong": "#c4c4c4",
        "text": "#202020",
        "text_strong": "#000000",
        "text_muted": "#5c5c5c",
        "text_dim": "#737373",
        "button": "#ffffff",
        "button_hover": "#f2f2f2",
        "button_pressed": "#e6e6e6",
        "button_border": "#c8c8c8",
        "accent": "#0067b8",
        "accent_hover": "#0078d4",
        "accent_pressed": "#005a9e",
        "accent_text": "#ffffff",
        "selection": "#cfe8fb",
        "selection_text": "#10233a",
        "onair": "#c42b1c",
        "scrollbar": "#c9c9c9",
        "scrollbar_hover": "#b5b5b5",
    },
}


def _format_duration(seconds: int) -> str:
    if not seconds or seconds <= 0:
        return "—"
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _format_clock(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


class SeekSlider(QSlider):
    """Horizontal slider that jumps to the clicked position."""

    def __init__(self, parent=None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setObjectName("seekSlider")
        self.setRange(0, 0)
        self.setSingleStep(1000)
        self.setPageStep(10000)
        self.setTracking(True)

    def _value_at(self, x: float) -> int:
        return QStyle.sliderValueFromPosition(
            self.minimum(),
            self.maximum(),
            int(max(0, min(x, self.width()))),
            max(1, self.width()),
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.button() == Qt.MouseButton.LeftButton and self.maximum() > 0:
            self.setSliderDown(True)
            self.setValue(self._value_at(event.position().x()))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if self.isSliderDown() and self.maximum() > 0:
            self.setValue(self._value_at(event.position().x()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if self.isSliderDown():
            self.setValue(self._value_at(event.position().x()))
            self.setSliderDown(False)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class ChannelFetchThread(QThread):
    """Fetch a channel's video list off the GUI thread."""

    fetched = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self, scraper: ChannelScraper, url: str, max_videos: Optional[int] = None
    ) -> None:
        super().__init__()
        self._scraper = scraper
        self._url = url
        self._max_videos = max_videos

    def run(self) -> None:
        try:
            videos = self._scraper.fetch_videos(
                self._url, max_videos=self._max_videos
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        if videos:
            self.fetched.emit(videos)
        else:
            self.failed.emit("No videos found for this channel")


class CoverFetchThread(QThread):
    """Fetch missing cover art for an existing audio file."""

    ready = pyqtSignal(str, object)   # audio path, cover path or None
    failed = pyqtSignal(str, str)     # audio path, message

    def __init__(self, downloader, path: str, video_id: Optional[str]) -> None:
        super().__init__()
        self._downloader = downloader
        self._path = path
        self._video_id = video_id

    def run(self) -> None:
        try:
            cover = self._downloader.fetch_cover_for_file(
                self._path, self._video_id
            )
        except Exception as exc:
            self.failed.emit(self._path, str(exc))
            return
        self.ready.emit(self._path, cover)


class MainWindow(QMainWindow):
    """Application shell: now-playing card, playlist table, controls, tray."""

    tray_activated = pyqtSignal()
    playlist_changed = pyqtSignal()
    track_changed = pyqtSignal(str)
    playback_stopped = pyqtSignal()
    playback_error = pyqtSignal(str)
    channel_videos_found = pyqtSignal(object, str)

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self._metadata: dict[str, dict] = {}
        self._track_history: list[str] = []
        self._max_history = 50
        self._cover_cache: dict[tuple[str, int], QPixmap] = {}
        self._cover_threads: list["CoverFetchThread"] = []
        self._fetch_thread: Optional[ChannelFetchThread] = None
        self._fetch_channel_url = ""
        self._on_air_state: Optional[str] = None
        self._force_quit = False
        self._shut_down = False
        self._current_theme = "dark"
        self._resume_position_pending: Optional[float] = None
        self._last_saved_resume: tuple[str, int] | None = None
        self._last_track_path = ""

        self._engine = AudioEngine(
            download_path=self.config.download_path,
            audio_format=self.config.audio_format,
        )
        self._engine.on_track_changed(self.track_changed.emit)
        self._engine.on_playlist_changed(self.playlist_changed.emit)
        self._engine.on_playback_stopped(self.playback_stopped.emit)
        self._engine.on_error(self.playback_error.emit)

        self._yt_downloader = YouTubeDownloader(
            download_path=self.config.download_path,
            audio_format=self.config.audio_format,
            audio_quality=self.config.audio_quality,
        )
        self._download_queue = DownloadQueue(self._yt_downloader, self)
        self._yt_scraper = ChannelScraper(
            max_videos=self.config.get("max_videos_per_fetch", 10)
        )
        self._scheduler = ChannelUpdater(
            config=self.config,
            channel_scraper=self._yt_scraper,
            youtube_downloader=self._yt_downloader,
            audio_engine=self._engine,
            on_videos_found=self.channel_videos_found.emit,
        )

        self._build_ui()
        self._connect_signals()
        self._apply_theme(config.theme)
        self._setup_tray()
        self._wire_engine_settings()
        self._load_playlist()

        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(1000)
        self._ui_timer.timeout.connect(self._tick_ui)
        self._ui_timer.start()
        self._tick_ui()

        self._save_timer = QTimer(self)
        self._save_timer.setInterval(10000)
        self._save_timer.timeout.connect(self._save_resume_state)
        self._save_timer.start()

        self._resume_timer = QTimer(self)
        self._resume_timer.setInterval(100)
        self._resume_timer.timeout.connect(self._apply_pending_resume)

        # A radio should already be on air when it opens.
        if self.config.autoplay and self._engine.playlist():
            QTimer.singleShot(600, self._autostart_playback)

        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._shutdown)

        if self.config.scheduler_enabled:
            self._scheduler.start()

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------
    def _connect_signals(self) -> None:
        self.playlist_changed.connect(self._on_playlist_changed)
        self.track_changed.connect(self._on_track_changed)
        self.playback_stopped.connect(self._on_playback_stopped)
        self.playback_error.connect(self._on_playback_error)
        self.channel_videos_found.connect(self._on_scheduler_videos)
        self._download_queue.changed.connect(self._refresh_queue_table)
        self._download_queue.item_updated.connect(self._on_queue_item_updated)
        self._download_queue.item_finished.connect(self._on_queue_item_finished)
        self._download_queue.active_changed.connect(self._on_queue_active_changed)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.setWindowTitle("Freevoice Radio")
        self.resize(960, 640)
        self.setAcceptDrops(True)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # ---- Menu bar ----
        menubar = self.menuBar()

        file_menu = menubar.addMenu("File")
        add_folder_action = QAction("Add Local Folder…", self)
        add_folder_action.triggered.connect(self._choose_local_folder)
        file_menu.addAction(add_folder_action)

        remove_action = QAction("Remove Selected Track", self)
        remove_action.triggered.connect(self._remove_selected_tracks)
        file_menu.addAction(remove_action)

        delete_action = QAction("Delete Selected File(s)…", self)
        delete_action.triggered.connect(self._delete_selected_tracks)
        file_menu.addAction(delete_action)

        clear_action = QAction("Clear Playlist", self)
        clear_action.triggered.connect(self._clear_playlist)
        file_menu.addAction(clear_action)

        file_menu.addSeparator()
        quit_action = QAction("Exit", self)
        quit_action.triggered.connect(self._quit_app)
        file_menu.addAction(quit_action)

        channel_menu = menubar.addMenu("Channel")
        self._channel_menu = channel_menu
        self.btn_add_channel = QAction("Add YouTube Channel…", self)
        self.btn_add_channel.triggered.connect(self._add_channel_dialog)
        channel_menu.addAction(self.btn_add_channel)

        manage_channels = QAction("Manage Channels…", self)
        manage_channels.triggered.connect(self._manage_channels)
        channel_menu.addAction(manage_channels)

        self.btn_add_url = QAction("Add YouTube Video URL…", self)
        self.btn_add_url.triggered.connect(self._add_youtube_url_dialog)
        channel_menu.addAction(self.btn_add_url)

        channel_menu.addSeparator()

        settings_menu = menubar.addMenu("Settings")
        settings_action = QAction("Preferences…", self)
        settings_action.triggered.connect(self._open_settings)
        settings_menu.addAction(settings_action)

        # ---- Now playing card ----
        self.now_playing_card = QFrame()
        self.now_playing_card.setObjectName("nowPlayingCard")
        self.now_playing_card.setFixedHeight(140)
        np_layout = QHBoxLayout(self.now_playing_card)

        self.cover_label = QLabel()
        self.cover_label.setObjectName("coverArt")
        self.cover_label.setFixedSize(100, 100)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setText("No\nCover")
        np_layout.addWidget(self.cover_label)

        info_layout = QVBoxLayout()
        self.title_label = QLabel("No track playing")
        self.title_label.setObjectName("trackTitle")
        self.title_label.setWordWrap(True)
        self.artist_label = QLabel("Freevoice Radio")
        self.artist_label.setObjectName("trackArtist")
        self.source_label = QLabel("Source: —")
        self.source_label.setObjectName("trackSource")
        self.next_label = QLabel("Up next: —")
        self.next_label.setObjectName("trackNext")
        info_layout.addWidget(self.title_label)
        info_layout.addWidget(self.artist_label)
        info_layout.addWidget(self.source_label)
        info_layout.addWidget(self.next_label)
        info_layout.addStretch()
        np_layout.addLayout(info_layout, stretch=1)

        self.on_air_label = QLabel("○ OFF AIR")
        self.on_air_label.setObjectName("onAir")
        self.on_air_label.setProperty("onair", "false")
        self.on_air_label.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight
        )
        np_layout.addWidget(self.on_air_label)

        layout.addWidget(self.now_playing_card)

        # ---- Playlist search / reorder ----
        playlist_tools = QHBoxLayout()
        playlist_tools.addWidget(QLabel("Search:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter by title, artist or source…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setAcceptDrops(False)
        self.search_edit.textChanged.connect(self._on_search_changed)
        playlist_tools.addWidget(self.search_edit, stretch=1)

        self.btn_move_up = QPushButton("Move Up")
        self.btn_move_up.setToolTip("Move the selected track up (Alt+Up)")
        self.btn_move_up.clicked.connect(lambda: self._move_selected(-1))
        self.btn_move_down = QPushButton("Move Down")
        self.btn_move_down.setToolTip("Move the selected track down (Alt+Down)")
        self.btn_move_down.clicked.connect(lambda: self._move_selected(1))
        playlist_tools.addWidget(self.btn_move_up)
        playlist_tools.addWidget(self.btn_move_down)
        layout.addLayout(playlist_tools)

        # ---- Playlist table ----
        self.playlist_table = QTableWidget(0, 5)
        self.playlist_table.setHorizontalHeaderLabels(
            ["#", "Title", "Artist", "Source", "Duration"]
        )
        self.playlist_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.playlist_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.playlist_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.playlist_table.setAcceptDrops(False)
        self.playlist_table.setDragDropMode(QTableWidget.DragDropMode.NoDragDrop)
        self.playlist_table.verticalHeader().setVisible(False)
        self.playlist_table.verticalHeader().setDefaultSectionSize(48)
        self.playlist_table.setIconSize(QSize(40, 40))
        self.playlist_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Fixed
        )
        self.playlist_table.setColumnWidth(0, 48)
        self.playlist_table.cellDoubleClicked.connect(self._play_row)
        self.playlist_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.playlist_table.customContextMenuRequested.connect(
            self._show_playlist_menu
        )
        self._remove_shortcut = QShortcut(
            QKeySequence("Delete"), self.playlist_table
        )
        self._remove_shortcut.activated.connect(self._remove_selected_tracks)
        self._delete_shortcut = QShortcut(
            QKeySequence("Shift+Delete"), self.playlist_table
        )
        self._delete_shortcut.activated.connect(self._delete_selected_tracks)
        self._move_up_shortcut = QShortcut(
            QKeySequence("Alt+Up"), self.playlist_table
        )
        self._move_up_shortcut.activated.connect(lambda: self._move_selected(-1))
        self._move_down_shortcut = QShortcut(
            QKeySequence("Alt+Down"), self.playlist_table
        )
        self._move_down_shortcut.activated.connect(lambda: self._move_selected(1))
        layout.addWidget(self.playlist_table, stretch=1)

        # ---- Track progress / air-time ----
        progress_row = QHBoxLayout()
        self.seek_slider = SeekSlider()
        self.seek_slider.setEnabled(False)
        self.seek_slider.setFixedHeight(18)
        self.seek_slider.valueChanged.connect(self._on_seek_changed)
        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setObjectName("trackTime")
        progress_row.addWidget(self.seek_slider, stretch=1)
        progress_row.addWidget(self.time_label)
        layout.addLayout(progress_row)

        # ---- Controls ----
        controls = QHBoxLayout()

        self.btn_prev = QPushButton("Prev")
        self.btn_play = QPushButton("Play")
        self.btn_play.setObjectName("playButton")
        self.btn_next = QPushButton("Next")
        self.btn_stop = QPushButton("Stop")

        self.btn_prev.clicked.connect(self._prev_track)
        self.btn_play.clicked.connect(self._toggle_playback)
        self.btn_next.clicked.connect(self._next_track)
        self.btn_stop.clicked.connect(self._stop_playback)

        self.btn_loop = QPushButton("Repeat All")
        self.btn_loop.setToolTip("Cycle repeat: All → One → Off")
        self.btn_loop.clicked.connect(self._cycle_loop_mode)

        self.btn_shuffle = QPushButton("Shuffle")
        self.btn_shuffle.setToolTip("Play the playlist in random order")
        self.btn_shuffle.setCheckable(True)
        self.btn_shuffle.clicked.connect(self._toggle_shuffle)

        controls.addWidget(self.btn_prev)
        controls.addWidget(self.btn_play)
        controls.addWidget(self.btn_next)
        controls.addWidget(self.btn_stop)
        controls.addWidget(self.btn_loop)
        controls.addWidget(self.btn_shuffle)
        controls.addStretch()

        controls.addWidget(QLabel("Vol:"))
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(self.config.volume)
        self.volume_slider.setFixedWidth(120)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        controls.addWidget(self.volume_slider)

        # ---- Download progress bar ----
        self.download_progress = QProgressBar()
        self.download_progress.setRange(0, 100)
        self.download_progress.setValue(0)
        self.download_progress.setFixedWidth(200)
        self.download_progress.hide()
        controls.addWidget(self.download_progress)

        self.download_status = QLabel("")
        self.download_status.setFixedWidth(230)
        self.download_status.hide()
        controls.addWidget(self.download_status)

        layout.addLayout(controls)

        # ---- Download queue dock ----
        self.queue_dock = QDockWidget("Download Queue", self)
        self.queue_dock.setObjectName("downloadQueueDock")
        self.queue_dock.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea
            | Qt.DockWidgetArea.TopDockWidgetArea
        )

        queue_widget = QWidget()
        queue_layout = QVBoxLayout(queue_widget)
        queue_layout.setContentsMargins(6, 6, 6, 6)

        self.queue_table = QTableWidget(0, 4)
        self.queue_table.setHorizontalHeaderLabels(
            ["Track", "Source", "Progress", "Status"]
        )
        self.queue_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.queue_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.queue_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.queue_table.verticalHeader().setVisible(False)
        queue_layout.addWidget(self.queue_table)

        queue_buttons = QHBoxLayout()
        self.btn_queue_cancel = QPushButton("Cancel Current")
        self.btn_queue_cancel.clicked.connect(self._queue_cancel)
        self.btn_queue_retry = QPushButton("Retry Selected")
        self.btn_queue_retry.clicked.connect(self._queue_retry)
        self.btn_queue_remove = QPushButton("Remove Selected")
        self.btn_queue_remove.clicked.connect(self._queue_remove)
        self.btn_queue_clear = QPushButton("Clear Finished")
        self.btn_queue_clear.clicked.connect(self._queue_clear_finished)
        for button in (
            self.btn_queue_cancel,
            self.btn_queue_retry,
            self.btn_queue_remove,
            self.btn_queue_clear,
        ):
            queue_buttons.addWidget(button)
        queue_buttons.addStretch()
        queue_layout.addLayout(queue_buttons)

        self.queue_dock.setWidget(queue_widget)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.queue_dock)
        self._queue_toggle_action = self.queue_dock.toggleViewAction()
        self._queue_toggle_action.setText("Download Queue")
        self._channel_menu.addAction(self._queue_toggle_action)
        self.queue_dock.hide()

        self.statusBar().showMessage("Ready")

    # ------------------------------------------------------------------
    # Theme / tray
    # ------------------------------------------------------------------
    def _apply_theme(self, theme: str) -> None:
        qss_path = os.path.join(os.path.dirname(__file__), "themes.qss")
        try:
            with open(qss_path, "r", encoding="utf-8") as handle:
                template = handle.read()
        except OSError:
            template = ""

        if theme == "system":
            theme = self._system_theme()
        theme = "light" if theme == "light" else "dark"

        colors = THEME_COLORS[theme]
        qss = template
        # Longest first: @text must not eat @text_strong.
        for token in sorted(colors, key=len, reverse=True):
            qss = qss.replace("@" + token, colors[token])

        self.setProperty("theme", theme)
        self._current_theme = theme
        qss = qss.replace(
            "@gui_dir", os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
        )
        app = QApplication.instance()
        if app is not None:
            # App-wide so dialogs, menus and docks follow the theme too.
            app.setStyleSheet(qss)
        else:
            self.setStyleSheet(qss)
        QTimer.singleShot(0, lambda: self._apply_titlebar(theme))

    def _apply_titlebar(self, theme: str) -> None:
        """Match the native title bar to the in-app theme on Windows."""
        if os.name != "nt":
            return
        try:
            import ctypes

            value = ctypes.c_int(0 if theme == "light" else 1)
            hwnd = int(self.winId())
            for attribute in (20, 19):  # DwmSetWindowAttribute ids
                result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
                )
                if result == 0:
                    break
        except Exception:
            pass

    def _system_theme(self) -> str:
        app = QGuiApplication.instance()
        if not app:
            return "dark"
        window_color = app.palette().color(QPalette.ColorRole.Window)
        return "dark" if window_color.lightness() < 128 else "light"

    def _app_icon(self) -> QIcon:
        """Small built-in station icon (blue disc + white play triangle)."""
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#007acc"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(2, 2, 60, 60)
        painter.setBrush(QColor("#ffffff"))
        painter.drawPolygon(
            QPolygon([QPoint(25, 18), QPoint(25, 46), QPoint(47, 32)])
        )
        painter.end()
        return QIcon(pixmap)

    def _setup_tray(self) -> None:
        icon = self._app_icon()
        self.setWindowIcon(icon)

        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(icon)
        self.tray.setToolTip("Freevoice Radio — on air")
        self.tray.activated.connect(self._on_tray_activated)

        tray_menu = QMenu()
        show_action = QAction("Show Freevoice Radio", self)
        show_action.triggered.connect(self.show_normal)
        play_action = QAction("Play / Pause", self)
        play_action.triggered.connect(self._toggle_playback)
        next_action = QAction("Next Track", self)
        next_action.triggered.connect(self._next_track)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._quit_app)

        tray_menu.addAction(show_action)
        tray_menu.addAction(play_action)
        tray_menu.addAction(next_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)
        self.tray.setContextMenu(tray_menu)

        # Always expose the tray icon: it is how a hidden radio is found again.
        self.tray.show()

    # ------------------------------------------------------------------
    # Playlist loading / persistence
    # ------------------------------------------------------------------
    def _wire_engine_settings(self) -> None:
        """Apply config values to the audio engine."""
        self._engine.set_loop_mode(self.config.loop_mode)
        self._engine.set_shuffle(self.config.shuffle)
        self._engine.set_gapless(self.config.gapless)
        self._engine.set_crossfade(
            self.config.crossfade_enabled, self.config.crossfade_seconds
        )
        self._engine.set_silence(
            self.config.silence_between_tracks, self.config.silence_seconds
        )
        self._engine.set_volume(self.config.volume)
        self._update_transport_buttons()

    def _load_playlist(self) -> None:
        """Restore the saved playlist, then merge the configured local folder."""
        entries: dict[str, dict] = {}

        for entry in self.config.playlist:
            path = self._normalize(resolve_path(entry.get("path")))
            if not path or not os.path.isfile(path):
                continue
            if self.config.is_excluded(path):
                continue
            entries[path] = {
                "path": path,
                "title": entry.get("title") or self._title_for(path),
                "artist": entry.get("artist") or "Unknown",
                "duration": int(entry.get("duration") or 0),
                "source": entry.get("source") or "local",
                "cover": entry.get("cover"),
                "video_id": entry.get("video_id"),
            }

        folder = self.config.local_folder
        if folder and os.path.isdir(folder):
            for name in sorted(os.listdir(folder)):
                path = self._normalize(os.path.join(folder, name))
                if not self._is_playable_file(path) or not os.path.isfile(path):
                    continue
                if self.config.is_excluded(path):
                    continue
                entries.setdefault(path, self._local_metadata(path))

        # Tracks sitting in the download folder always belong to the radio.
        download_dir = self.config.download_path
        if download_dir and os.path.isdir(download_dir):
            for name in sorted(os.listdir(download_dir)):
                path = self._normalize(os.path.join(download_dir, name))
                if not self._is_playable_file(path) or not os.path.isfile(path):
                    continue
                if self.config.is_excluded(path):
                    continue
                entries.setdefault(
                    path,
                    {
                        "path": path,
                        "title": self._title_for(path),
                        "artist": "YouTube",
                        "duration": 0,
                        "source": "youtube",
                    },
                )

        self._metadata.update(entries)
        self._engine.set_playlist(list(entries.keys()))
        self._refresh_playlist_table()
        self._persist_playlist()

    def _persist_playlist(self) -> None:
        entries = []
        seen: set[str] = set()
        for raw_path in self._engine.playlist():
            path = self._normalize(raw_path)
            key = os.path.normcase(path)
            if key in seen:
                continue
            seen.add(key)
            meta = self._metadata.get(path) or self._local_metadata(path)
            entries.append(
                {
                    "path": path,
                    "title": meta.get("title") or self._title_for(path),
                    "artist": meta.get("artist") or "Unknown",
                    "duration": int(meta.get("duration") or 0),
                    "source": meta.get("source") or "local",
                    "cover": meta.get("cover") or self._cover_path(path),
                    "video_id": meta.get("video_id")
                    or (
                        self._yt_downloader.video_id_for_file(path)
                        if hasattr(self, "_yt_downloader")
                        else None
                    ),
                }
            )
        self.config.playlist = entries
        self.config.save()

    @staticmethod
    def _normalize(path: str) -> str:
        return os.path.normpath(os.path.abspath(path)) if path else path

    def _title_for(self, path: str) -> str:
        return os.path.splitext(os.path.basename(path))[0]

    # ------------------------------------------------------------------
    # Cover art
    # ------------------------------------------------------------------
    def _cover_candidates(self, path: str):
        meta = self._metadata.get(path) or {}
        configured = meta.get("cover")
        if configured and os.path.isfile(configured):
            yield configured

        stem = os.path.splitext(path)[0]
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            candidate = stem + ext
            if os.path.isfile(candidate):
                yield candidate

        folder = os.path.dirname(path)
        if os.path.normcase(folder) != os.path.normcase(self.config.download_path):
            for name in ("cover.jpg", "folder.jpg", "album.jpg", "cover.png"):
                candidate = os.path.join(folder, name)
                if os.path.isfile(candidate):
                    yield candidate

    def _cover_path(self, path: str) -> Optional[str]:
        for candidate in self._cover_candidates(path):
            if os.path.getsize(candidate) > 0:
                return candidate
        return None

    def _cover_pixmap(self, path: str, size: int) -> QPixmap:
        key = (path, size)
        if key in self._cover_cache:
            return self._cover_cache[key]
        for candidate in self._cover_candidates(path):
            pixmap = QPixmap(candidate)
            if pixmap.isNull():
                continue
            pixmap = pixmap.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = max(0, (pixmap.width() - size) // 2)
            y = max(0, (pixmap.height() - size) // 2)
            result = pixmap.copy(x, y, size, size)
            self._cover_cache[key] = result
            return result
        empty = QPixmap()
        self._cover_cache[key] = empty
        return empty

    def _update_cover_label(self, path: str) -> None:
        pixmap = self._cover_pixmap(path, 100)
        if pixmap.isNull():
            self.cover_label.clear()
            self.cover_label.setText("No\nCover")
        else:
            self.cover_label.setText("")
            self.cover_label.setPixmap(pixmap)

    def _download_cover_art(self, path: str) -> None:
        path = self._normalize(path)
        if self._cover_path(path):
            self.statusBar().showMessage("This track already has cover art")
            return
        video_id = (self._metadata.get(path) or {}).get("video_id")
        if not video_id:
            video_id = self._yt_downloader.video_id_for_file(path)
        if not video_id:
            QMessageBox.information(
                self,
                "Download Cover Art",
                "This file is not linked to a YouTube video, so no cover "
                "art can be downloaded.\n\n"
                f"File: {os.path.basename(path)}",
            )
            return

        thread = CoverFetchThread(self._yt_downloader, path, video_id)
        thread.ready.connect(self._on_cover_ready)
        thread.failed.connect(self._on_cover_failed)
        thread.finished.connect(self._on_cover_thread_finished)
        self._cover_threads.append(thread)
        thread.start()
        self.statusBar().showMessage("Downloading cover art…")

    def _on_cover_ready(self, path: str, cover: object) -> None:
        if not cover or not os.path.isfile(str(cover)):
            self.statusBar().showMessage("No cover art available for this video")
            return
        meta = self._metadata.setdefault(path, self._local_metadata(path))
        meta["cover"] = str(cover)
        self._cover_cache.clear()
        if self._engine.current_track() == path:
            self._update_cover_label(path)
        self._refresh_playlist_table()
        self._persist_playlist()
        self.statusBar().showMessage(
            f"Cover art saved: {os.path.basename(str(cover))}"
        )

    def _on_cover_failed(self, path: str, message: str) -> None:
        print(f"[cover] {path}: {message}")
        self.statusBar().showMessage(f"Cover art failed: {message}")

    def _on_cover_thread_finished(self) -> None:
        thread = self.sender()
        if thread in self._cover_threads:
            self._cover_threads.remove(thread)
        if thread is not None:
            thread.deleteLater()

    @staticmethod
    def _is_playable_file(path: str) -> bool:
        name = os.path.basename(path).lower()
        if not name.endswith(AUDIO_EXTENSIONS):
            return False
        # yt-dlp's intermediate container for audio-only YouTube streams.
        # The converted file is the library entry; importing the .webm too
        # would list (and loop) the same track twice.
        if name.endswith(".webm"):
            return False
        # Legacy artefact of the old pygame backend; never a playlist entry.
        return not name.endswith("_converted.wav")

    def _local_metadata(self, path: str) -> dict:
        download_dir = os.path.normcase(self.config.download_path or "")
        source = (
            "youtube"
            if download_dir and os.path.normcase(os.path.dirname(path)) == download_dir
            else "local"
        )
        return {
            "path": path,
            "title": self._title_for(path),
            "artist": "YouTube" if source == "youtube" else "Unknown",
            "duration": 0,
            "source": source,
            "cover": self._cover_path(path),
            "video_id": (
                self._yt_downloader.video_id_for_file(path)
                if hasattr(self, "_yt_downloader")
                else None
            ),
        }

    def _on_playlist_changed(self) -> None:
        self._refresh_playlist_table()
        self._persist_playlist()

    def _refresh_playlist_table(self) -> None:
        paths = self._engine.playlist()
        current = self._engine.current_track()
        self.playlist_table.setRowCount(len(paths))
        for row, path in enumerate(paths):
            meta = self._metadata.get(path) or self._local_metadata(path)
            title = meta.get("title") or self._title_for(path)
            values = [
                str(row + 1),
                title,
                meta.get("artist") or "Unknown",
                meta.get("source") or "local",
                _format_duration(int(meta.get("duration") or 0)),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setToolTip(path)
                self.playlist_table.setItem(row, column, item)
            cover = self._cover_pixmap(path, 40)
            if not cover.isNull():
                self.playlist_table.item(row, 1).setIcon(QIcon(cover))
            if path == current:
                font = self.playlist_table.item(row, 1).font()
                font.setBold(True)
                self.playlist_table.item(row, 1).setFont(font)

            term = self.search_edit.text().strip().lower()
            visible = not term or any(term in str(value).lower() for value in values)
            self.playlist_table.setRowHidden(row, not visible)
        self._update_next_label()

    def _on_track_changed(self, file_path: str) -> None:
        if file_path in self._track_history:
            self._track_history.remove(file_path)
        self._track_history.insert(0, file_path)
        self._track_history = self._track_history[: self._max_history]
        self._last_track_path = file_path
        if (
            self._resume_position_pending is not None
            and file_path != self.config.resume_track
        ):
            self._resume_position_pending = None

        meta = self._metadata.get(file_path) or self._local_metadata(file_path)
        title = meta.get("title") or self._title_for(file_path)
        self.title_label.setText(title)
        self.artist_label.setText(meta.get("artist") or "Unknown")
        source = meta.get("source") or "local"
        self.source_label.setText(
            "Source: YouTube" if source == "youtube" else f"Source: {source}"
        )
        self.setWindowTitle(f"{title} — Freevoice Radio")
        self._update_cover_label(file_path)
        self._update_transport_buttons()
        self._update_on_air()
        self._refresh_playlist_table()
        if self._resume_position_pending is None:
            self._save_resume_state(force=True)

    def _on_playback_stopped(self) -> None:
        self.btn_play.setText("▶ Play")
        self._update_on_air()
        self._refresh_playlist_table()

    def _on_playback_error(self, message: str) -> None:
        self.statusBar().showMessage(message, 8000)
        print(f"[audio] {message}")

    # ------------------------------------------------------------------
    # Download queue
    # ------------------------------------------------------------------
    def _add_to_queue(
        self, url: str, title: str = "", source: str = "url", stream: bool = False
    ):
        item = self._download_queue.add(
            url, title=title, source=source, stream=stream
        )
        if item is None:
            return None
        self.queue_dock.show()
        self._refresh_queue_table()
        self.statusBar().showMessage(f"Queued: {title or url}")
        return item

    def _refresh_queue_table(self) -> None:
        items = self._download_queue.items
        self.queue_table.setRowCount(len(items))
        for row, item in enumerate(items):
            self._apply_queue_row(row, item)
        if items:
            self.queue_dock.show()

    def _queue_row_for_uid(self, uid: int):
        for row in range(self.queue_table.rowCount()):
            cell = self.queue_table.item(row, 0)
            if cell is not None and cell.data(Qt.ItemDataRole.UserRole) == uid:
                return row
        return None

    def _apply_queue_row(self, row: int, item) -> None:
        title_item = QTableWidgetItem(item.title or item.url)
        title_item.setData(Qt.ItemDataRole.UserRole, item.uid)
        title_item.setToolTip(item.url)
        title_item.setFlags(title_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.queue_table.setItem(row, 0, title_item)
        self.queue_table.setItem(row, 1, QTableWidgetItem(item.source))
        progress = (
            f"{item.percent}%"
            if item.is_active or item.status == "Done"
            else "—"
        )
        self.queue_table.setItem(row, 2, QTableWidgetItem(progress))
        status_text = item.detail or item.status
        if item.status == "Failed" and item.error:
            status_text = item.error
        status_item = QTableWidgetItem(status_text)
        status_item.setToolTip(item.error or status_text)
        status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.queue_table.setItem(row, 3, status_item)

    def _on_queue_item_updated(self, item) -> None:
        row = self._queue_row_for_uid(item.uid)
        if row is None:
            self._refresh_queue_table()
        else:
            self._apply_queue_row(row, item)
        current = self._download_queue.current_item()
        if current is not None and current.uid == item.uid:
            self._update_compact_download(item)

    def _update_compact_download(self, item) -> None:
        self.download_progress.show()
        self.download_status.show()
        self.download_progress.setValue(max(0, min(int(item.percent), 100)))
        self.download_status.setText(item.detail or item.status)

    def _on_queue_active_changed(self, active: bool) -> None:
        current = self._download_queue.current_item()
        if active and current is not None:
            self._update_compact_download(current)
            return
        self.download_progress.hide()
        self.download_status.hide()
        pending = self._download_queue.pending_count()
        if pending == 0:
            self.statusBar().showMessage("Download queue idle")

    def _on_queue_item_finished(self, item, track: YouTubeTrack) -> None:
        if self._shut_down:
            return
        if not track or not track.file_path:
            return
        path = self._normalize(track.file_path)
        if not os.path.exists(path):
            return
        self.config.include(path)
        self._metadata[path] = {
            "path": path,
            "title": track.title or self._title_for(path),
            "artist": track.artist or "YouTube",
            "duration": int(track.duration or 0),
            "source": "stream" if item.stream else "youtube",
            "cover": track.cover_path,
            "video_id": track.id,
        }
        self._cover_cache.clear()
        self._engine.add_track(path, stream=item.stream)
        self._refresh_playlist_table()
        self._persist_playlist()
        if not self._engine.is_playing() and not self._engine.is_paused():
            self._engine.play_track(path)
        self.statusBar().showMessage(f"Added: {track.title}")

    def _selected_queue_items(self):
        selected = []
        for row in sorted({index.row() for index in self.queue_table.selectedIndexes()}):
            cell = self.queue_table.item(row, 0)
            if cell is None:
                continue
            item = self._download_queue.item_by_uid(cell.data(Qt.ItemDataRole.UserRole))
            if item is not None:
                selected.append(item)
        return selected

    def _queue_cancel(self) -> None:
        if self._download_queue.is_active():
            self._download_queue.cancel_current()
            self.statusBar().showMessage("Cancelling current download…")
        else:
            self.statusBar().showMessage("Nothing is downloading")

    def _queue_retry(self) -> None:
        items = self._selected_queue_items()
        if not items:
            self.statusBar().showMessage("Select a failed download first")
            return
        for item in items:
            self._download_queue.retry(item)

    def _queue_remove(self) -> None:
        items = self._selected_queue_items()
        if not items:
            self.statusBar().showMessage("Select a download first")
            return
        for item in items:
            self._download_queue.remove(item)
        self._refresh_queue_table()

    def _queue_clear_finished(self) -> None:
        self._download_queue.clear_finished()
        self._refresh_queue_table()

    def _on_scheduler_videos(self, videos, channel_url: str) -> None:
        added = 0
        skipped = 0
        for video in videos:
            if self._yt_downloader._find_audio_file(video.id):
                skipped += 1
                continue
            if self._download_queue.add(
                video.url,
                title=video.title,
                source="channel",
                stream=self.config.youtube_mode == "stream",
            ):
                added += 1
        if added:
            self.queue_dock.show()
            self._refresh_queue_table()
            self.statusBar().showMessage(
                f"Channel update: queued {added} video(s)"
                + (f", skipped {skipped} already downloaded" if skipped else "")
            )

    def _manage_channels(self) -> None:
        from src.gui.channels_dialog import ChannelsDialog

        dialog = ChannelsDialog(self.config, self)
        dialog.exec()
        if dialog.video_url:
            self._add_youtube_url(dialog.video_url)
        elif dialog.fetch_url:
            self._start_channel_fetch(dialog.fetch_url)
        self._scheduler.stop()
        if self.config.scheduler_enabled:
            self._scheduler.start()

    # ------------------------------------------------------------------
    # Tray / window lifecycle
    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().showEvent(event)
        self._apply_titlebar(self._current_theme)

    def show_normal(self) -> None:
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_normal()
            self.tray_activated.emit()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if self._force_quit:
            self._shutdown()
            event.accept()
            return

        action = self.config.close_action
        if action == "tray":
            event.ignore()
            self._minimize_to_tray()
            return
        if action == "quit":
            self._shutdown()
            event.accept()
            return

        choice = self._ask_close_action()
        if choice == "tray":
            event.ignore()
            self._minimize_to_tray()
        elif choice == "quit":
            self._shutdown()
            event.accept()
        else:
            event.ignore()

    def _ask_close_action(self) -> Optional[str]:
        """Ask whether the close button should hide or quit."""
        box = QMessageBox(self)
        box.setWindowTitle("Close Freevoice Radio")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText("Keep the radio on air in the system tray, or close the app?")
        box.setInformativeText(
            "Minimize to Tray keeps playback running. Close App stops the radio "
            "and exits completely."
        )
        tray_button = box.addButton(
            "Minimize to Tray", QMessageBox.ButtonRole.AcceptRole
        )
        box.addButton("Close App", QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = box.addButton(QMessageBox.StandardButton.Cancel)
        remember = QCheckBox("Remember my choice")
        box.setCheckBox(remember)
        box.setDefaultButton(tray_button)
        box.exec()

        clicked = box.clickedButton()
        if clicked is None or clicked is cancel_button:
            return None
        action = "tray" if clicked is tray_button else "quit"
        if remember.isChecked():
            self.config.close_action = action
            self.config.save()
        return action

    def _minimize_to_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.showNormal()
            QMessageBox.warning(
                self,
                "System tray unavailable",
                "Windows did not provide a system tray, so the window stays open.",
            )
            return
        self.hide()
        self.tray.show()
        self.statusBar().showMessage("Still on air in the system tray")
        self.tray.showMessage(
            "Freevoice Radio",
            "Still on air. If you don't see the icon, click the ^ arrow in the "
            "taskbar to show hidden tray icons.",
            QSystemTrayIcon.MessageIcon.Information,
            4000,
        )

    def _shutdown(self) -> None:
        if self._shut_down:
            return
        self._shut_down = True
        try:
            self._download_queue.stop()
        except Exception:
            traceback.print_exc()
        for thread in list(self._cover_threads):
            try:
                thread.wait(3000)
            except RuntimeError:
                pass
        if self._fetch_thread is not None:
            try:
                self._fetch_thread.wait(3000)
            except RuntimeError:
                pass
        try:
            self._persist_playlist()
        except Exception:
            traceback.print_exc()
        try:
            self._scheduler.stop()
        except Exception:
            traceback.print_exc()
        try:
            self._save_resume_state(force=True)
        except Exception:
            traceback.print_exc()
        try:
            self._engine.quit()
        except Exception:
            traceback.print_exc()
        try:
            self.tray.hide()
        except Exception:
            pass

    def _quit_app(self) -> None:
        self._force_quit = True
        self._shutdown()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    # ------------------------------------------------------------------
    # Playback controls
    # ------------------------------------------------------------------
    def _toggle_playback(self) -> None:
        if self._engine.is_playing():
            self._engine.pause()
        elif self._engine.is_paused():
            self._engine.resume()
        else:
            if not self._engine.play():
                self.statusBar().showMessage(
                    "Nothing to play: add a folder or a YouTube URL first"
                )
        self._update_transport_buttons()
        self._update_on_air()
        self._refresh_playlist_table()
        self._save_resume_state(force=True)
        self.statusBar().showMessage(
            "Paused" if self._engine.is_paused() else
            ("Playing" if self._engine.is_playing() else "Stopped")
        )

    def _update_play_button_text(self) -> None:
        if self._engine.is_playing():
            self.btn_play.setText("Pause")
        else:
            self.btn_play.setText("Play")

    # ------------------------------------------------------------------
    # Repeat / shuffle / on-air state
    # ------------------------------------------------------------------
    @staticmethod
    def _set_button_active(button: QPushButton, active: bool) -> None:
        if button.property("active") == active:
            return
        button.setProperty("active", active)
        button.style().unpolish(button)
        button.style().polish(button)

    def _update_transport_buttons(self) -> None:
        mode = self._engine.loop_mode()
        labels = {
            "all": "Repeat All",
            "one": "Repeat One",
            "off": "Repeat Off",
        }
        tips = {
            "all": "Repeating the whole playlist (click for Repeat One)",
            "one": "Repeating the current track (click to turn repeat off)",
            "off": "Repeat is off (click for Repeat All)",
        }
        self.btn_loop.setText(labels.get(mode, labels["all"]))
        self.btn_loop.setToolTip(tips.get(mode, tips["all"]))
        self._set_button_active(self.btn_loop, mode != "off")

        shuffle = self._engine.shuffle_enabled()
        self.btn_shuffle.setText("Shuffle On" if shuffle else "Shuffle")
        self.btn_shuffle.setChecked(shuffle)
        self._set_button_active(self.btn_shuffle, shuffle)

        self._update_play_button_text()
        self._update_next_label()

    def _cycle_loop_mode(self) -> None:
        order = ["all", "one", "off"]
        current = self._engine.loop_mode()
        next_mode = (
            order[(order.index(current) + 1) % len(order)]
            if current in order
            else "all"
        )
        self._engine.set_loop_mode(next_mode)
        self.config.loop_mode = {
            "all": "loop_all",
            "one": "loop_one",
            "off": "off",
        }[next_mode]
        self.config.save()
        self._update_transport_buttons()
        self.statusBar().showMessage(f"Repeat: {next_mode.capitalize()}")

    def _toggle_shuffle(self) -> None:
        enabled = bool(self.btn_shuffle.isChecked())
        self._engine.set_shuffle(enabled)
        self.config.shuffle = enabled
        self.config.save()
        self._update_transport_buttons()
        self.statusBar().showMessage("Shuffle on" if enabled else "Shuffle off")

    def _update_on_air(self) -> None:
        if self._engine.is_playing():
            state, text = "on", "● ON AIR"
        elif self._engine.is_paused():
            state, text = "paused", "❚❚ STANDBY"
        else:
            state, text = "off", "○ OFF AIR"
        if state == self._on_air_state:
            return
        self._on_air_state = state
        self.on_air_label.setText(text)
        self.on_air_label.setProperty("onair", "true" if state == "on" else "false")
        self.on_air_label.style().unpolish(self.on_air_label)
        self.on_air_label.style().polish(self.on_air_label)

    def _apply_pending_resume(self) -> None:
        if self._resume_position_pending is None:
            self._resume_timer.stop()
            return
        duration = self._engine.duration()
        if duration <= 0:
            return
        target = min(
            self._resume_position_pending, max(0.0, duration - 1.0)
        )
        self._engine.seek(target)
        self._resume_position_pending = None
        self._resume_timer.stop()
        self.statusBar().showMessage(
            f"Resumed at {_format_clock(target)}", 4000
        )

    def _tick_ui(self) -> None:
        self._update_on_air()
        duration = self._engine.duration()
        position = self._engine.position()
        if self._resume_position_pending is not None and duration > 0:
            target = min(self._resume_position_pending, max(0.0, duration - 1.0))
            self._engine.seek(target)
            position = target
            self._resume_position_pending = None
        if duration > 0:
            if not self.seek_slider.isSliderDown():
                self.seek_slider.blockSignals(True)
                self.seek_slider.setRange(0, int(duration * 1000))
                self.seek_slider.setValue(min(int(position * 1000), int(duration * 1000)))
                self.seek_slider.blockSignals(False)
                self.time_label.setText(
                    f"{_format_clock(position)} / {_format_clock(duration)}"
                )
            self.seek_slider.setEnabled(True)
        else:
            if not self.seek_slider.isSliderDown():
                self.seek_slider.blockSignals(True)
                self.seek_slider.setRange(0, 0)
                self.seek_slider.setValue(0)
                self.seek_slider.blockSignals(False)
                self.time_label.setText("0:00 / 0:00")
            self.seek_slider.setEnabled(False)
        self._update_next_label()

    def _on_seek_changed(self, value: int) -> None:
        if self._resume_position_pending is not None:
            self._resume_timer.stop()
        self._resume_position_pending = None
        duration = self._engine.duration()
        if duration <= 0:
            return
        self.time_label.setText(
            f"{_format_clock(value / 1000.0)} / {_format_clock(duration)}"
        )
        self._engine.seek(value / 1000.0)

    def _update_next_label(self) -> None:
        if not hasattr(self, "next_label"):
            return
        if not (self._engine.is_playing() or self._engine.is_paused()):
            self.next_label.setText("Up next: —")
            return
        path = self._engine.peek_next_path()
        if path:
            meta = self._metadata.get(path) or self._local_metadata(path)
            title = meta.get("title") or self._title_for(path)
            if len(title) > 80:
                title = title[:77] + "…"
            self.next_label.setText(f"Up next: {title}")
            self.next_label.setToolTip(path)
        elif self._engine.shuffle_enabled() and self._engine.playlist():
            self.next_label.setText("Up next: Shuffle")
        else:
            self.next_label.setText("Up next: —")

    def _on_search_changed(self, _text: str) -> None:
        self._refresh_playlist_table()

    def _move_selected(self, offset: int) -> None:
        paths = self._selected_paths()
        if not paths:
            self.statusBar().showMessage("Select a track to reorder")
            return
        path = paths[0]
        if not self._engine.move_track(path, offset):
            self.statusBar().showMessage("Track is already at the end")
            return
        index = self._engine.playlist().index(path)
        self._refresh_playlist_table()
        if 0 <= index < self.playlist_table.rowCount() and not self.playlist_table.isRowHidden(index):
            self.playlist_table.selectRow(index)
        title = (self._metadata.get(path) or {}).get("title") or self._title_for(path)
        self.statusBar().showMessage(f"Moved: {title}")

    # ------------------------------------------------------------------
    # Drag and drop
    # ------------------------------------------------------------------
    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt API)
        paths = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.isLocalFile()
        ]
        if paths:
            self._add_local_paths(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    def _add_local_paths(self, raw_paths: list[str]) -> None:
        added = 0
        for raw in raw_paths:
            path = self._normalize(raw)
            if os.path.isdir(path):
                candidates = [
                    self._normalize(os.path.join(path, name))
                    for name in sorted(os.listdir(path))
                ]
            else:
                candidates = [path]
            for candidate in candidates:
                if not self._is_playable_file(candidate) or not os.path.isfile(candidate):
                    continue
                self.config.include(candidate)
                self._metadata.setdefault(candidate, self._local_metadata(candidate))
                if self._engine.add_track(candidate):
                    added += 1
        self._refresh_playlist_table()
        self._persist_playlist()
        if added:
            self.statusBar().showMessage(f"Added {added} track(s) from drop")
        else:
            self.statusBar().showMessage("No supported audio files in the drop")

    def _autostart_playback(self) -> None:
        """Start the radio automatically, resuming the last track/position."""
        if self._shut_down:
            return
        if self._engine.is_playing() or self._engine.is_paused():
            return
        if not self._engine.playlist():
            self.statusBar().showMessage("Add music to go on air")
            return

        resume_path = self.config.resume_track
        resume_position = self.config.resume_position
        started = False
        if (
            resume_path
            and resume_path in self._engine.playlist()
            and os.path.isfile(resume_path)
        ):
            self._resume_position_pending = (
                resume_position if resume_position > 1.0 else None
            )
            started = self._engine.play_track(resume_path)
            if started and self._resume_position_pending is not None:
                self._resume_timer.start()
                self.statusBar().showMessage(
                    f"Resuming at {_format_clock(resume_position)}"
                )
        if not started:
            self._resume_position_pending = None
            started = self._engine.play()

        if started:
            self._update_transport_buttons()
            if self._resume_position_pending is None:
                self.statusBar().showMessage("ON AIR — playing")
        else:
            self.statusBar().showMessage("Add music to go on air")

    def _save_resume_state(self, force: bool = False) -> None:
        """Remember the current track and position for the next launch."""
        path = self._engine.current_track() or self._last_track_path
        if not path or not os.path.isfile(path):
            return
        if self._engine.is_playing() or self._engine.is_paused():
            position = self._engine.position()
        else:
            position = 0.0
        if position < 1.0 and self._resume_position_pending is not None:
            position = self._resume_position_pending

        snapshot = (path, int(position))
        if not force and snapshot == self._last_saved_resume:
            return
        self.config.resume_track = path
        self.config.resume_position = position
        self.config.save()
        self._last_saved_resume = snapshot

    def _prev_track(self) -> None:
        if not self._engine.playlist():
            return
        self._resume_position_pending = None
        self._engine.prev_track()
        self._update_transport_buttons()

    def _next_track(self) -> None:
        if not self._engine.playlist():
            return
        self._resume_position_pending = None
        self._engine.next_track()
        self._update_transport_buttons()

    def _stop_playback(self) -> None:
        self._resume_position_pending = None
        self._engine.stop()
        self._save_resume_state(force=True)
        self.btn_play.setText("▶ Play")
        self._update_on_air()
        self.statusBar().showMessage("Stopped")

    def _play_row(self, row: int, _column: int) -> None:
        paths = self._engine.playlist()
        if 0 <= row < len(paths):
            self._resume_position_pending = None
            self._engine.play_track(paths[row])
            self._update_transport_buttons()
            self._update_on_air()

    def _selected_paths(self) -> list[str]:
        rows = sorted({index.row() for index in self.playlist_table.selectedIndexes()})
        paths = self._engine.playlist()
        return [paths[row] for row in rows if 0 <= row < len(paths)]

    def _show_playlist_menu(self, position: QPoint) -> None:
        index = self.playlist_table.indexAt(position)
        if not index.isValid():
            return
        row = index.row()
        if row not in {item.row() for item in self.playlist_table.selectedIndexes()}:
            self.playlist_table.selectRow(row)
        paths = self._selected_paths()
        if not paths:
            return

        menu = QMenu(self)
        play_action = menu.addAction("▶ Play")
        copy_action = menu.addAction("Copy Path")
        cover_action = None
        if len(paths) == 1 and not self._cover_path(paths[0]):
            cover_action = menu.addAction("Download Cover Art")
        menu.addSeparator()
        remove_action = menu.addAction("Remove from Playlist")
        remove_action.setToolTip("Keep the file on disk, hide it from the playlist")
        delete_label = (
            "Delete File from Disk…"
            if len(paths) == 1
            else f"Delete {len(paths)} Files from Disk…"
        )
        delete_action = menu.addAction(delete_label)

        chosen = menu.exec(self.playlist_table.viewport().mapToGlobal(position))
        if chosen == play_action:
            self._play_row(row, 0)
        elif chosen == copy_action:
            QApplication.clipboard().setText(paths[0])
            self.statusBar().showMessage("Path copied")
        elif cover_action is not None and chosen == cover_action:
            self._download_cover_art(paths[0])
        elif chosen == remove_action:
            self._remove_tracks(paths)
        elif chosen == delete_action:
            self._delete_tracks(paths, confirm=True)

    def _remove_selected_tracks(self) -> None:
        paths = self._selected_paths()
        if not paths:
            self.statusBar().showMessage("Select one or more rows first")
            return
        self._remove_tracks(paths)

    def _delete_selected_tracks(self) -> None:
        paths = self._selected_paths()
        if not paths:
            self.statusBar().showMessage("Select one or more rows first")
            return
        self._delete_tracks(paths, confirm=True)

    def _remove_tracks(self, paths: list[str]) -> None:
        """Remove tracks from the playlist but keep their files."""
        if not paths:
            return
        normalized = [self._normalize(path) for path in paths]
        current = self._engine.current_track()
        was_playing = self._engine.is_playing()
        if current in normalized:
            self._engine.stop()

        for path in normalized:
            self._engine.remove_track(path)
            self.config.exclude(path)
            self._metadata.pop(path, None)
            self._track_history = [
                item
                for item in self._track_history
                if os.path.normcase(item) != os.path.normcase(path)
            ]

        self.config.save()
        self._persist_playlist()
        self._refresh_playlist_table()
        if was_playing and current in normalized and self._engine.playlist():
            self._engine.play()
            self._update_transport_buttons()
            self._update_on_air()
        self.statusBar().showMessage(
            f"Removed {len(normalized)} track(s) from the playlist (files kept)"
        )

    def _delete_tracks(self, paths: list[str], confirm: bool = True) -> None:
        """Delete audio files from disk and remove them from the playlist."""
        if not paths:
            return
        normalized = [self._normalize(path) for path in paths]

        if confirm:
            names = "\n".join(f"• {os.path.basename(p)}" for p in normalized[:10])
            if len(normalized) > 10:
                names += f"\n…and {len(normalized) - 10} more"
            box = QMessageBox(self)
            box.setWindowTitle("Delete from disk")
            box.setIcon(QMessageBox.Icon.Warning)
            box.setText(f"Permanently delete {len(normalized)} file(s)?")
            box.setInformativeText(f"{names}\n\nThis cannot be undone.")
            box.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            box.setDefaultButton(QMessageBox.StandardButton.No)
            if box.exec() != QMessageBox.StandardButton.Yes:
                return

        current = self._engine.current_track()
        was_playing = self._engine.is_playing()
        if current in normalized:
            # Release the file handle before deleting the playing track.
            self._engine.stop()
            QApplication.processEvents()
            time.sleep(0.1)
            QApplication.processEvents()

        errors: list[str] = []
        for path in normalized:
            error = self._delete_file(path)
            if error:
                errors.append(f"{os.path.basename(path)}: {error}")
            self._engine.remove_track(path)
            self.config.include(path)
            self._metadata.pop(path, None)
            self._track_history = [
                item
                for item in self._track_history
                if os.path.normcase(item) != os.path.normcase(path)
            ]

        self.config.save()
        self._persist_playlist()
        self._refresh_playlist_table()
        if was_playing and current in normalized and self._engine.playlist():
            self._engine.play()
            self._update_transport_buttons()
            self._update_on_air()

        if errors:
            QMessageBox.warning(
                self, "Delete failed", "Could not delete:\n" + "\n".join(errors)
            )
        else:
            self.statusBar().showMessage(f"Deleted {len(normalized)} file(s)")

    def _delete_file(self, path: str) -> Optional[str]:
        """Delete one file, retrying while the player releases its handle."""
        path = self._normalize(path)
        error: Optional[str] = None
        if os.path.exists(path):
            for _ in range(25):
                try:
                    os.remove(path)
                    error = None
                    break
                except FileNotFoundError:
                    error = None
                    break
                except PermissionError:
                    # QMediaPlayer releases the file asynchronously; let the
                    # event loop run so the handle can close.
                    error = "file is in use"
                    QApplication.processEvents()
                    time.sleep(0.2)
                except OSError as exc:
                    error = str(exc)
                    break

        # Remove downloaded leftovers that belong to this track.
        folder = os.path.dirname(path)
        if os.path.normcase(folder) == os.path.normcase(self.config.download_path):
            stem = os.path.splitext(os.path.basename(path))[0]
            for ext in ("webm", "m4a", "mp4", "opus", "ogg", "aac", "part", "ytdl"):
                candidate = os.path.join(folder, f"{stem}.{ext}")
                if os.path.normcase(candidate) != os.path.normcase(path) and os.path.exists(
                    candidate
                ):
                    try:
                        os.remove(candidate)
                    except OSError:
                        pass
            converted = os.path.join(folder, f"{stem}_converted.wav")
            if os.path.exists(converted):
                try:
                    os.remove(converted)
                except OSError:
                    pass
            for ext in ("jpg", "jpeg", "png", "webp"):
                cover = os.path.join(folder, f"{stem}.{ext}")
                if os.path.exists(cover):
                    try:
                        os.remove(cover)
                    except OSError:
                        pass
            self._yt_downloader.forget_file(path)
        return error

    def _clear_playlist(self) -> None:
        if not self._engine.playlist():
            return
        answer = QMessageBox.question(
            self,
            "Clear Playlist",
            "Remove every track from the playlist?\n"
            "The files stay on disk and are not re-imported automatically.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            for path in self._engine.playlist():
                self.config.exclude(path)
            self._engine.clear_playlist()
            self.config.save()
            self.statusBar().showMessage("Playlist cleared (files kept)")

    def _on_volume_changed(self, value: int) -> None:
        self.config.volume = value
        self._engine.set_volume(value)
        self.config.save()
        self.statusBar().showMessage(f"Volume: {value}%")

    # ------------------------------------------------------------------
    # Menu actions
    # ------------------------------------------------------------------
    def _choose_local_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Local Audio Folder")
        if not folder:
            return
        self.config.local_folder = folder
        self.config.save()
        added = 0
        for name in sorted(os.listdir(folder)):
            path = self._normalize(os.path.join(folder, name))
            if not self._is_playable_file(path) or not os.path.isfile(path):
                continue
            self.config.include(path)
            if self._engine.add_track(path):
                self._metadata.setdefault(path, self._local_metadata(path))
                added += 1
        self._refresh_playlist_table()
        self.config.save()
        self.statusBar().showMessage(f"Folder: {folder} ({added} new track(s))")

    def _add_channel_dialog(self) -> None:
        url, ok = QInputDialog.getText(
            self, "Add YouTube Channel", "Channel URL (or a single video URL):"
        )
        if not ok or not url.strip():
            return
        url = url.strip()

        # Users often paste a video URL here; treat it as a single video.
        if video_id_from_url(url):
            self._add_youtube_url(url)
            return

        channel = {
            "id": url,
            "name": url,
            "url": url,
            "enabled": True,
            "last_checked": None,
            "max_videos_per_fetch": self.config.get("max_videos_per_fetch", 10),
        }
        self.config.add_channel(channel)
        self.config.save()
        self.statusBar().showMessage(f"Channel added: {url}")
        self._start_channel_fetch(url)

    def _add_youtube_url_dialog(self) -> None:
        url, ok = QInputDialog.getText(self, "Add YouTube Video", "Video URL:")
        if ok and url.strip():
            self._add_youtube_url(url.strip())

    def _add_youtube_url(self, url: str) -> None:
        """Queue a YouTube URL for download."""
        if self._add_to_queue(
            url,
            source="url",
            stream=self.config.youtube_mode == "stream",
        ) is None:
            self.statusBar().showMessage("Enter a valid YouTube URL")

    # ------------------------------------------------------------------
    # Channel fetching
    # ------------------------------------------------------------------
    def _start_channel_fetch(self, channel_url: str) -> None:
        if self._fetch_thread and self._fetch_thread.isRunning():
            self.statusBar().showMessage("A channel fetch is already running")
            return
        channel = next(
            (
                item
                for item in self.config.channels
                if (item.get("url") or item.get("id")) == channel_url
            ),
            None,
        )
        max_videos = (
            int(channel.get("max_videos_per_fetch") or 10) if channel else None
        )
        self._fetch_thread = ChannelFetchThread(
            self._yt_scraper, channel_url, max_videos=max_videos
        )
        self._fetch_channel_url = channel_url
        self._fetch_thread.fetched.connect(self._on_channel_videos_fetched)
        self._fetch_thread.failed.connect(self._on_channel_fetch_failed)
        self._fetch_thread.finished.connect(self._on_channel_fetch_finished)
        self._fetch_thread.start()
        self.statusBar().showMessage(f"Fetching videos for {channel_url}…")

    def _on_channel_fetch_finished(self) -> None:
        thread = self.sender()
        if thread is self._fetch_thread:
            self._fetch_thread = None
        if thread is not None:
            thread.deleteLater()

    def _on_channel_videos_fetched(self, videos) -> None:
        if not videos:
            self.statusBar().showMessage("No videos found for this channel")
            return
        from src.gui.channel_videos_dialog import ChannelVideosDialog

        channel_url = getattr(self, "_fetch_channel_url", "")
        channel_name = next(
            (
                item.get("name") or item.get("url") or ""
                for item in self.config.channels
                if (item.get("url") or item.get("id")) == channel_url
            ),
            channel_url,
        )
        dialog = ChannelVideosDialog(
            self,
            channel_name=channel_name,
            videos=list(videos),
            is_downloaded=lambda video: bool(
                self._yt_downloader._find_audio_file(video.id)
            ),
        )
        if not dialog.exec():
            self.statusBar().showMessage("Channel selection cancelled")
            return

        selected = dialog.selected_videos()
        if not selected:
            self.statusBar().showMessage("No videos selected")
            return

        added = 0
        for video in selected:
            if self._download_queue.add(
                video.url,
                title=video.title,
                source="channel",
                stream=self.config.youtube_mode == "stream",
            ):
                added += 1
        if added:
            self.queue_dock.show()
            self._refresh_queue_table()
        self.statusBar().showMessage(f"Channel: queued {added} selected video(s)")

    def _on_channel_fetch_failed(self, message: str) -> None:
        self.statusBar().showMessage(f"Channel fetch failed: {message}")
        QMessageBox.warning(self, "Channel", message)

    def _open_settings(self) -> None:
        from src.gui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(self.config, self)
        if not dialog.exec():
            return

        # Apply the new values to running components.
        self._wire_engine_settings()
        self._apply_theme(self.config.theme)
        self._yt_downloader.download_path = self.config.download_path
        self._yt_downloader.audio_format = self.config.audio_format
        self._yt_downloader.audio_quality = self.config.audio_quality
        try:
            os.makedirs(self.config.download_path, exist_ok=True)
        except OSError as exc:
            self.statusBar().showMessage(f"Download folder is not usable: {exc}")
        self.config.save()

        # The tray is how a hidden radio is found again; keep it available.
        self.tray.show()

        self._scheduler.stop()
        if self.config.scheduler_enabled:
            self._scheduler.start()

        self.statusBar().showMessage("Settings saved")
