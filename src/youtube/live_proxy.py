"""Local HLS proxy for YouTube live audio.

QtMultimedia can decode HLS, but YouTube's live segment URLs require the
headers that yt-dlp negotiated.  This tiny localhost proxy fetches the remote
playlist/segments with those headers and rewrites playlist URLs so the media
player only ever talks to 127.0.0.1.
"""

from __future__ import annotations

import re
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional


class _Handler(BaseHTTPRequestHandler):
    server_version = "FreevoiceLiveProxy/1.0"

    def log_message(self, *_args) -> None:  # silence per-segment logging
        pass

    def _target(self) -> Optional[str]:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/live.m3u8":
            return self.server.remote_url  # type: ignore[attr-defined]
        if parsed.path == "/proxy":
            params = urllib.parse.parse_qs(parsed.query)
            return params.get("u", [""])[0]
        return None

    def _local(self, url: str) -> str:
        return "/proxy?u=" + urllib.parse.quote(url, safe="")

    def _rewrite(self, text: str, base_url: str) -> bytes:
        lines: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                lines.append(line)
                continue
            if stripped.startswith("#"):
                if 'URI="' in line:
                    line = re.sub(
                        r'URI="([^"]+)"',
                        lambda m: 'URI="'
                        + self._local(urllib.parse.urljoin(base_url, m.group(1)))
                        + '"',
                        line,
                    )
                lines.append(line)
            else:
                lines.append(self._local(urllib.parse.urljoin(base_url, stripped)))
        return "\n".join(lines).encode("utf-8")

    def do_GET(self) -> None:  # noqa: N802 (HTTP API)
        target = self._target()
        if not target:
            self.send_error(404)
            return
        try:
            request = urllib.request.Request(
                target, headers=self.server.headers  # type: ignore[attr-defined]
            )
            with urllib.request.urlopen(request, timeout=25) as response:
                data = response.read()
                content_type = response.headers.get(
                    "Content-Type", "application/octet-stream"
                )
            is_playlist = target.split("?")[0].lower().endswith(".m3u8") or data.startswith(
                b"#EXTM3U"
            )
            if is_playlist:
                data = self._rewrite(data.decode("utf-8", "replace"), target)
                content_type = "application/vnd.apple.mpegurl"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:
            print(f"[live-proxy] {target[:100]}: {exc}")
            try:
                self.send_error(502)
            except Exception:
                pass

    def do_HEAD(self) -> None:  # noqa: N802 (HTTP API)
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.apple.mpegurl")
        self.end_headers()


class LiveProxyServer:
    """Serve one live HLS playlist through localhost with custom headers."""

    def __init__(self, remote_url: str, headers: dict[str, str]) -> None:
        self.remote_url = remote_url
        self.headers = dict(headers or {})
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.daemon_threads = True
        self._server.remote_url = remote_url  # type: ignore[attr-defined]
        self._server.headers = self.headers  # type: ignore[attr-defined]
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True
        )
        self._thread.start()

    @property
    def local_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}/live.m3u8"

    def stop(self) -> None:
        try:
            self._server.shutdown()
            self._server.server_close()
        except Exception:
            pass
