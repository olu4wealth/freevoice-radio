# Freevoice Radio

A 24/7 local radio desktop application for Windows that plays YouTube audio
and local audio files on a continuous loop. Not an online streaming platform —
everything plays from local files or downloaded audio on your PC.

## Features

- **YouTube audio playback** — Download audio-only from YouTube, originally or converted
- **Original audio mode** — Keeps YouTube's Opus/M4A stream and skips FFmpeg conversion
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

### File size and disk space

New downloads default to **Original (no conversion)**: the app keeps YouTube's
audio-only Opus/M4A file and plays it directly. This starts faster and avoids
the conversion step; the source is roughly **120 kbps**, or about **54 MB per
hour**.

MP3 is optional. Its size is roughly `bitrate × duration / 8`:

| Quality | 1 hour | Your 83-minute track |
|---------|--------|----------------------|
| 96 kbps | ~42 MB | ~58 MB |
| 128 kbps | ~56 MB | ~78 MB |
| 192 kbps | ~84 MB | ~117 MB |

YouTube serves audio at roughly 120 kbps (Opus), so converting it to a
192 kbps MP3 actually **increases** the size. Choose the format under
Settings → YouTube → **Format**. **MP3 Quality** only applies when converting
to MP3. Existing files are never re-encoded — MP3 files stay exactly as they
are.

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

### Closing the app

Clicking the window's close button asks what to do:

- **Minimize to Tray** — keeps the radio playing; find it via the tray icon.
- **Close App** — stops playback and exits.
- **Remember my choice** — stores the answer; change it later under
  Settings → General → *When I click the close button*.

The tray icon is a blue disc with a white play triangle. Windows 11 hides new
tray icons in the **^** overflow area the first time. If it is not there:
Settings → Personalization → Taskbar → **Other system tray icons**, and enable
Freevoice Radio. The app also has **Settings → General → Open Windows taskbar
settings…** for this.

If the window is hidden and you cannot find the icon, just start Freevoice
Radio again: the single-instance guard brings the existing window back.

### Single instance

Only one radio runs at a time. If you launch the app again — double-clicking
the exe, the Start menu shortcut, or Windows startup — the existing window is
brought to the front and the second process exits.

### Start with Windows

Settings → General → **Start Freevoice Radio with Windows (minimized to tray)**
is **off by default**. When enabled it adds a per-user entry under
`HKCU\Software\Microsoft\Windows\CurrentVersion\Run` (no admin rights needed).
Windows launches it as `"…\Freevoice Radio.exe" --minimized`, so it starts
hidden in the tray and, if Autoplay is on, resumes the last track and position.
Turning the checkbox off removes the entry.

### Live streams

**Channel → Play YouTube Live…** (or the **Live** button) accepts a live video
URL or a channel URL (`@handle`, `/channel/UC…`, `/c/…`, `/user/…`). A prefix
of `/live` is added automatically for channel URLs.

- **Channel → Manage Channels… → Play Live** opens the selected channel's
  `/live` broadcast.
- The live stream is played **directly from YouTube's HLS audio**, not
  downloaded as a file. Only a small rolling buffer is kept.
- The now-playing card shows **● LIVE**; seeking, previous/next, loop and
  shuffle are disabled while live.
- Play/Pause and the volume slider control the live player.
- If the stream stalls or the manifest expires, the app re-resolves and
  reconnects automatically (up to two attempts), then returns to the playlist.
- Stopping live returns to the paused radio track/position.

Live audio uses roughly **58 MB per hour** at 128 kbps; it does not use the
download folder or MP3 quality setting.

### Streaming watchdog

While a **stream** track (YouTube mode = Stream) is playing, the app checks the
playback position every second. If it has not advanced for 15 seconds, it
reloads the stream and seeks back to the last position. After two failed
restarts it skips to the next track. Downloaded files are never restarted by
the watchdog.

Downloaded YouTube files are named after the video title, e.g.
`SOAK IN HIS PRESENCE A Powerful Worship Experience.webm` in Original mode
(or `.mp3` when converting). A hidden
`downloads/.freevoice_index.json` remembers which video each file came from,
so re-adding a URL does not download it twice. Name collisions get ` (2)`.

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
| MP3 quality | 96 / 128 / 160 / 192 / 256 / 320 kbps (conversion only) |
| Loop mode | Loop All, Loop One, Off |
| Start with Windows | Off by default; launches minimized to tray at login |
| Shuffle | On / Off |
| Auto-start | Play when the app opens |
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
    ├── single_instance.py  # Lock/socket name for one running app
    ├── startup.py          # Optional HKCU Windows startup entry
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
    │   └── live_proxy.py  # Localhost HLS proxy with YouTube headers
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
| App is playing but I can't find the window | Start Freevoice Radio again — the single-instance guard restores the hidden window. Then use the tray icon. |
| Tray icon missing from the **^** overflow | Windows Settings → Personalization → Taskbar → **Other system tray icons** → enable Freevoice Radio. Settings → General also has a button that opens this page. |
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