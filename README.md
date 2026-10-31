# Freevoice Radio

A 24/7 local radio desktop application for Windows that plays YouTube audio
and local audio files on a continuous loop. Not an online streaming platform —
everything plays from local files or downloaded audio on your PC.

## Features

- **YouTube audio playback** — Download audio-only from YouTube, originally or converted
- **Original audio mode** — Keeps YouTube's Opus/M4A stream and skips FFmpeg conversion
- **Updatable yt-dlp** — Download the latest extractor from PyPI without rebuilding the app
- **Sleep prevention** — Keeps the computer awake while radio or live audio is playing
- **Live YouTube audio** — Play a live video or channel directly via HLS, with reconnect
- **Local audio playback** — Play MP3, WAV, FLAC, M4A, OGG, AAC from any folder
- **Continuous loop** — Loop All / Loop One / Shuffle / Off modes
- **Channel-based playlist updates** — Add YouTube channels; download the videos you pick
- **Download queue** — Sequential downloads with cancel, retry, remove and clear
- **Background scheduler** — Optional, per-channel auto-download on a configurable interval
- **Gapless playback** — Seamless transitions between tracks (toggleable)
- **Crossfade** — Fade between tracks (toggleable, configurable seconds)
- **Silence between tracks** — Insert silence gaps (toggleable, configurable seconds)
- **Volume control** — 0–100%
- **System tray** — Minimize to tray, app keeps running
- **Themes** — Dark / Light / System
- **Track history** — Last 50 played tracks recorded automatically
- **Auto-cleanup** — Deletes downloaded files older than 48 hours not in the playlist
- **Persistent playlist** — Downloads are remembered across restarts
- **Resume playback** — On launch, continues the last track from where it stopped
- **Memory-light streaming** — Long tracks (multi-hour sets) stream from disk instead
  of being decoded into RAM, so they start immediately after download
- **Album art** — YouTube thumbnails are saved as `<title>.jpg` next to the audio
  and shown in the now-playing card and playlist
- **Seekable playback** — click or drag the progress bar to jump in a track
- **Library tools** — drag-and-drop, search/filter, reorder, Up Next
- **Single instance** — launching again wakes the running radio instead of starting a second copy
- **Optional Windows startup** — launch minimized to the tray at login
- **Stream watchdog** — restarts a stalled streaming track automatically

## Requirements

- Windows 10/11
- Python 3.10+
- ffmpeg (for audio extraction). Either put `ffmpeg.exe` next to the
  app / `main.py`, or have ffmpeg on `PATH`.

## Installation

```bash
cd freevoice-radio
pip install -r requirements.txt
```

## Usage

```bash
python main.py
```


### Self-test

Verify the audio pipeline without opening the UI:

```bash
python main.py --selftest          # plays a downloaded file for ~3 seconds
python main.py --selftest --audible
python main.py --selftest-loop     # checks end-of-track advance + looping
```

### First Run

1. **Add local audio**: File → Add Local Folder… to select a folder with your MP3s/etc.
2. **Add YouTube channel**: Channel → Add YouTube Channel… to fetch videos from a channel
3. **Add YouTube video**: Channel → Add YouTube Video URL… for a single video
4. **Configure**: Settings to adjust loop mode, shuffle, crossfade, silence, theme, etc.
5. **Play**: Click ▶ Play, or just leave the app open — it starts on air automatically

## On-air controls

| Control | Behaviour |
|---------|-----------|
| 🔁 Repeat All / One / Off | Cycles repeat mode. Repeat One loops the current track; Off stops after the playlist has played through once. |
| 🔀 Shuffle | Independent toggle. Plays the playlist in random order without repeating a track until the round is finished. |
| ● ON AIR | Turns red while audio is playing, shows STANDBY when paused. |
| Progress / time | Click or drag the bar to seek; shows elapsed and total time. |
| Up next | Shows the next track (or “Shuffle” when the order is random). |
| Auto-start | Starts playback when the app opens (can be disabled in Settings). |

### Playlist right-click menu

Right-click any row (multi-select works) for:

| Action | Behaviour |
|--------|-----------|
| ▶ Play | Start that track immediately |
| Copy Path | Copies the full file path to the clipboard |
| Download Cover Art | Fetches the YouTube thumbnail for a track that has no cover yet |
| Remove from Playlist | Hides the track but keeps the file. The path is remembered as excluded, so it is not auto-imported again |
| Delete File from Disk… | Permanently deletes the file after confirmation; downloaded leftovers (`.webm`) and index entries are cleaned up too |

Shortcuts: `Delete` removes selected rows from the playlist, `Shift+Delete` deletes the files.

### Searching, reordering and drag-and-drop

- The **Search** box filters by title, artist and source as you type.
- **Move Up / Move Down** (or `Alt+Up` / `Alt+Down`) reorders the playlist.
- Drag audio files or folders from Explorer onto the window to add them.
- **Up next** in the now-playing card shows the next track; with shuffle on it
  shows “Shuffle” when the random order is not yet decided.

### Download queue

Channel → Download Queue (or it opens automatically when something is queued).
Downloads run one at a time so ffmpeg conversions do not fight for CPU.

| Button | Behaviour |
|--------|-----------|
| Cancel Current | Aborts the active download; the queue moves to the next item |
| Retry Selected | Re-queues failed or cancelled downloads |
| Remove Selected | Drops the selected item from the queue |
| Clear Finished | Removes completed/failed/cancelled rows |

Each row shows its title, source (URL / channel / scheduler), progress and
status. Failed rows keep the error message as a tooltip. The compact progress
bar in the transport row mirrors the active download.



The update applies to new channel downloads, URL downloads, metadata and live
resolution. Restart Freevoice Radio after updating.

### Managing channels

Channel → Manage Channels… lists every configured channel with:

- **Auto-download** — off by default. Ticking it asks for confirmation and
  then downloads new videos from that channel automatically
- **Channel URL**
- **Last checked** timestamp
- **Videos** — how many recent videos to pull per poll

From there you can **Add Channel…**, **Remove Selected**, or **Browse Videos…**
to fetch the channel's latest list and tick exactly which videos to queue.
Downloaded videos are shown as such and cannot be selected twice. New channels
start with **Auto-download off**; the background scheduler only downloads from
channels you explicitly opted in, up to the channel's **Videos** limit.


### Resuming playback

The app remembers the current track and position in `config.json`
(`resume_track` and `resume_position`). It saves every 10 seconds, on track
changes, on pause/stop, and when the app closes. On the next launch it opens
that track and seeks back to the saved position. If the file was deleted it
falls back to the first track in the playlist.

This only starts audio automatically when **Autoplay** is enabled in Settings.
Pressing **Stop** saves position `0:00`; closing while playing or paused saves
the current position.

## Configuration

All settings are saved to `config.json` in the project folder. The Settings dialog
(Settings → Preferences) lets you change:

| Setting | Options |
|---------|---------|
| YouTube mode | Download (save to disk) / Stream (temp file) |
| Audio format | Original (no conversion), mp3, wav, flac, m4a |
| yt-dlp | Current version + Check for Updates (restart to activate) |
| MP3 quality | 96 / 128 / 160 / 192 / 256 / 320 kbps (conversion only) |
| Loop mode | Loop All, Loop One, Off |
| Start with Windows | Off by default; launches minimized to tray at login |
| Shuffle | On / Off |
| Auto-start | Play when the app opens |
| Prevent sleep | Keep the system awake while audio is playing (default on) |
| Gapless playback | On / Off |
| Crossfade | On / Off + seconds |
| Silence between tracks | On / Off + seconds |
| Volume | 0–100 |
| Theme | Dark, Light, System |
| System tray | Close button: Ask / Minimize to tray / Close app |
| Scheduler | On / Off + interval (minutes) |
| Auto-download | Per channel, **off by default**; ticking asks for confirmation |

## Project Structure

```
freevoice-radio/
├── main.py                 # Entry point (+ --selftest flags)
├── config.json             # Auto-generated settings + persisted playlist
├── requirements.txt        # Python dependencies
├── downloads/              # Downloaded YouTube audio (created at runtime)
├── assets/                 # Icons and default cover art (optional)
└── src/
    ├── app_paths.py        # Source/frozen paths + ffmpeg discovery
    ├── config.py           # Configuration manager
    ├── power.py            # Sleep prevention while playing
    ├── single_instance.py  # Lock/socket name for one running app
    ├── startup.py          # Optional HKCU Windows startup entry
    ├── ytdlp_runtime.py    # Load an external updated yt-dlp package
    ├── selftest.py         # Playback smoke tests
    ├── audio/
    │   ├── engine.py       # Playback engine (loop, crossfade, silence, streams)
    │   ├── backends.py     # QtMultimedia streaming backend + crossfade
    │   └── live_player.py  # HLS live audio player
    ├── gui/
    │   ├── main_window.py  # Main window, tray, controls, queue dock
    │   ├── channels_dialog.py  # Channel manager (enable/remove/browse)
    │   ├── channel_videos_dialog.py  # Pick videos from a channel
    │   ├── settings_dialog.py  # Settings dialog
    │   └── themes.qss      # Dark/light theme stylesheet
    ├── youtube/
    │   ├── downloader.py   # yt-dlp integration (download + progress + cancel)
    │   ├── download_queue.py  # Sequential queue with cancel/retry
    │   ├── channel_scraper.py  # Fetch videos from YouTube channels
    │   ├── live.py        # Resolve live YouTube URLs
    │   ├── live_proxy.py  # Localhost HLS proxy with YouTube headers
    │   └── updater.py     # Download/stage latest yt-dlp wheel
    ├── playlist/
    │   └── __init__.py     # Playlist package
    └── scheduler/
        └── updater.py      # Background channel polling + auto-cleanup
```

## License

Personal use.
