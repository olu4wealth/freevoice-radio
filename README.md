# Freevoice Radio

A 24/7 local radio desktop application for Windows that plays YouTube audio
and local audio files on a continuous loop. Not an online streaming platform —
everything plays from local files or downloaded audio on your PC.

## Features

- **YouTube audio playback** — Download audio-only from YouTube or stream via temp files
- **Local audio playback** — Play MP3, WAV, FLAC, M4A, OGG, AAC from any folder
- **Continuous loop** — Loop All / Loop One / Shuffle / Off modes
- **Channel-based playlist updates** — Add YouTube channels; app queues their latest videos automatically
- **Download queue** — Sequential downloads with cancel, retry, remove and clear
- **Background scheduler** — Polls enabled channels on a configurable interval (default: 60 min)
- **Gapless playback** — Seamless transitions between tracks (toggleable)
- **Crossfade** — Fade between tracks (toggleable, configurable seconds)
- **Silence between tracks** — Insert silence gaps (toggleable, configurable seconds)
- **Volume control** — 0–100%
- **System tray** — Minimize to tray, app keeps running
- **Themes** — Dark / Light / System
- **Track history** — Last 50 played tracks recorded automatically
- **Auto-cleanup** — Deletes downloaded files older than 48 hours not in the playlist
- **Persistent playlist** — Downloads are remembered across restarts
- **Memory-light streaming** — Long tracks (multi-hour sets) stream from disk instead
  of being decoded into RAM, so they start immediately after download
- **Album art** — YouTube thumbnails are saved as `<title>.jpg` next to the audio
  and shown in the now-playing card and playlist

## Requirements

- Windows 10/11
- Python 3.10+
- ffmpeg (for YouTube audio extraction). Either put `ffmpeg.exe` next to the
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

Audio playback uses QtMultimedia (bundled with PyQt6), so no extra audio
package is needed.  Downloaded audio is **not** converted to WAV anymore;
MP3/FLAC/M4A/OGG/WAV files stream directly from disk.

### Self-test

Verify the audio pipeline without opening the UI:

```bash
python main.py --selftest          # plays a downloaded file for ~3 seconds
python main.py --selftest --audible
python main.py --selftest-loop     # checks end-of-track advance + looping
```

The built executable supports the same flags and appends the output to
`freevoice.log` next to the exe.

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
| Progress / time | Shows elapsed and total time for the current track. |
| Auto-start | Starts playback when the app opens (can be disabled in Settings). |

### Playlist right-click menu

Right-click any row (multi-select works) for:

| Action | Behaviour |
|--------|-----------|
| ▶ Play | Start that track immediately |
| Remove from Playlist | Hides the track but keeps the file. The path is remembered as excluded, so it is not auto-imported again |
| Delete File from Disk… | Permanently deletes the file after confirmation; downloaded leftovers (`.webm`) and index entries are cleaned up too |

Shortcuts: `Delete` removes selected rows from the playlist, `Shift+Delete` deletes the files.

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

### Managing channels

Channel → Manage Channels… lists every configured channel with:

- **Enabled** — whether the background scheduler polls it
- **Channel URL**
- **Last checked** timestamp
- **Videos** — how many recent videos to pull per poll

From there you can **Add Channel…**, **Remove Selected**, or **Fetch Now** to
queue the channel's latest videos immediately. New videos found by the
scheduler are queued the same way, so unattended updates appear in the queue
and are added to the playlist as they finish.

### Closing the app

Clicking the window's close button asks what to do:

- **Minimize to Tray** — keeps the radio playing; find it via the tray icon.
- **Close App** — stops playback and exits.
- **Remember my choice** — stores the answer; change it later under
  Settings → General → *When I click the close button*.

The tray icon is always shown. Windows 11 hides new tray icons in the **^**
overflow area the first time; open it and drag the icon onto the taskbar to
keep it visible.

Downloaded YouTube files are named after the video title, e.g.
`SOAK IN HIS PRESENCE A Powerful Worship Experience.mp3`. A hidden
`downloads/.freevoice_index.json` remembers which video each file came from,
so re-adding a URL does not download it twice. Name collisions get ` (2)`.

## Configuration

All settings are saved to `config.json` in the project folder. The Settings dialog
(Settings → Preferences) lets you change:

| Setting | Options |
|---------|---------|
| YouTube mode | Download (save to disk) / Stream (temp file) |
| Audio format | mp3, wav, flac, m4a |
| Loop mode | Loop All, Loop One, Off |
| Shuffle | On / Off |
| Auto-start | Play when the app opens |
| Gapless playback | On / Off |
| Crossfade | On / Off + seconds |
| Silence between tracks | On / Off + seconds |
| Volume | 0–100 |
| Theme | Dark, Light, System |
| System tray | Close button: Ask / Minimize to tray / Close app |
| Scheduler | On / Off + interval (minutes) |

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
    ├── selftest.py         # Playback smoke tests
    ├── audio/
    │   ├── engine.py       # Playback engine (loop, crossfade, silence, streams)
    │   └── backends.py     # QtMultimedia streaming backend + crossfade
    ├── gui/
    │   ├── main_window.py  # Main window, tray, controls, queue dock
    │   ├── channels_dialog.py  # Channel manager (enable/remove/fetch now)
    │   ├── settings_dialog.py  # Settings dialog
    │   └── themes.qss      # Dark/light theme stylesheet
    ├── youtube/
    │   ├── downloader.py   # yt-dlp integration (download + progress + cancel)
    │   ├── download_queue.py  # Sequential queue with cancel/retry
    │   └── channel_scraper.py  # Fetch videos from YouTube channels
    ├── playlist/
    │   └── __init__.py     # Playlist package
    └── scheduler/
        └── updater.py      # Background channel polling + auto-cleanup
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Could not create temporary directory!` on launch | You are running an old one-file build. This version is an onedir build that never unpacks into `%TEMP%`; run `dist\Freevoice Radio.exe` from the rebuilt bundle. |
| Download reaches 100% but nothing plays | Fixed in this version: the completion handler now adds the track and starts playback. If it still happens, check `freevoice.log` next to the exe. |
| "ffmpeg not found" / download fails after 100% | Put `ffmpeg.exe` and `ffprobe.exe` next to `Freevoice Radio.exe` (or install ffmpeg and add it to `PATH`). |
| No sound at all | Open `python main.py --selftest --audible`; if it fails, Windows audio output or the QtMultimedia plugin is unavailable. |
| App is playing but I can't find the window | It is in the system tray. On Windows 11 click the **^** arrow near the clock; drag the Freevoice icon onto the taskbar to pin it. Double-click the icon to restore, or use tray → Quit to stop completely. |
| Closing the window hid the app instead of exiting | That is the close-button choice. Set Settings → General → *When I click the close button* to **Close the app**, or use File → Exit / tray → Quit. |
| `Failed to load Python DLL` / missing files | Keep `Freevoice Radio.exe` and the `_internal` folder together. Do not copy the exe on its own. |
| SmartScreen: "Windows protected your PC" | Expected for an unsigned, locally built exe. Click **More info → Run anyway**, run from source, or code-sign the build. |

### Why SmartScreen warns about the exe

SmartScreen is reputation-based, not an antivirus verdict. A locally built,
unsigned executable has no publisher signature and no download reputation, so
Windows shows the warning until enough users run the same signed binary. It is
not triggered by anything the app does. Options:

1. **Run anyway** — More info → Run anyway. One prompt per rebuilt exe.
2. **Use the included launcher** — double-click `Start Freevoice Radio.cmd` in
   `dist/`. It starts the exe directly, which avoids Explorer's SmartScreen
   prompt. Only use this for builds you compiled yourself from trusted source;
   it does not scan the file.
3. **Run from source** — `python main.py` is not subject to SmartScreen.
4. **Code-sign** — an OV/EV code-signing certificate removes the warning and
   builds reputation (EV certificates are trusted immediately). This is the
   proper fix if you distribute the app.
5. **Local exclusion** — for personal use you can exclude the `dist` folder in
   Windows Security, but that weakens protection; prefer 1, 2 or 4.

## Building the executable

```powershell
cd freevoice-radio
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_exe.ps1
```

(PowerShell refuses unsigned local scripts by default; `-ExecutionPolicy Bypass`
applies to this one command only.)

That runs PyInstaller with [Freevoice Radio.spec](<Freevoice Radio.spec>) and stages the
bundle into `dist/`: `Freevoice Radio.exe`, `_internal/`, and your existing
`config.json`, `downloads/`, `ffmpeg.exe` and `ffprobe.exe`.

The app is intentionally built as **onedir**, not one-file. A one-file exe has
to unpack itself into `%TEMP%` before it can start; on machines with a locked
down or filtered temp folder that fails with
`Could not create temporary directory!`. The onedir build runs in place, so it
needs no writable temp folder and starts faster.

Settings, `downloads/` and `freevoice.log` live next to the exe, so moving the
whole `dist` folder keeps your library; copying only the exe does not.

## License

Personal use. YouTube audio download is subject to YouTube's Terms of Service.