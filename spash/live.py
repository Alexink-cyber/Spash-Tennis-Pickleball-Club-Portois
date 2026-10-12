"""Diffusion en direct (YouTube ou tout service RTMP) avec le score incrusté."""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from typing import Callable

from . import ffmpeg as ff
from . import overlay
from .config import Court, LiveConfig

log = logging.getLogger(__name__)

OVERLAY_FPS = 2


class LiveStream:
    def __init__(self, ffmpeg: str, court: Court, cfg: LiveConfig, club_name: str,
                 get_score: Callable[[], tuple[dict | None, dict | None]]):
        self.ffmpeg = ffmpeg
        self.court = court
        self.cfg = cfg
        self.club_name = club_name
        self.get_score = get_score
        self.error: str | None = None
        self.started_at: float | None = None
        self._proc: subprocess.Popen | None = None
        self._stop = threading.Event()

    @property
    def target(self) -> str:
        # Une URL rtmp:// reçoit la clé de diffusion ; sinon c'est un fichier (tests).
        if self.cfg.rtmp_url.startswith(("rtmp://", "rtmps://")):
            return f"{self.cfg.rtmp_url}/{self.cfg.stream_key}"
        return self.cfg.rtmp_url

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        c = self.cfg
        bw, bh = overlay.banner_size(c.width, c.height)
        encoder = ["-c:v", c.encoder]
        if c.encoder == "libx264":
            encoder += ["-preset", "veryfast", "-tune", "zerolatency"]
        filters = (
            f"[0:v]scale={c.width}:{c.height}:force_original_aspect_ratio=decrease,"
            f"pad={c.width}:{c.height}:(ow-iw)/2:(oh-ih)/2,fps={c.fps},setpts=PTS-STARTPTS[bg];"
            f"[1:v]setpts=PTS-STARTPTS[ov];"
            f"[bg][ov]overlay=0:0:eof_action=repeat:repeatlast=1,format=yuv420p[v]"
        )
        cmd = [
            self.ffmpeg, "-hide_banner", "-loglevel", "error",
            *ff.camera_input_args(self.court),
            # Bandeau de score envoyé par Python ; pas d'analyse préalable (démarrage immédiat).
            "-probesize", "32", "-analyzeduration", "0",
            "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{bw}x{bh}",
            "-framerate", str(OVERLAY_FPS), "-i", "pipe:0",
            # YouTube exige une piste audio : on envoie du silence, au rythme réel
            # (sinon ffmpeg en produit trop vite et l'accumule en mémoire).
            "-re", "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-filter_complex", filters, "-map", "[v]", "-map", "2:a",
            *encoder, "-b:v", c.bitrate, "-maxrate", c.bitrate, "-bufsize", _double(c.bitrate),
            "-g", str(c.fps * 2), "-c:a", "aac", "-b:a", "128k",
            "-f", "flv", self.target,
        ]
        log.info("Terrain %s : démarrage du direct", self.court.id)
        self.error = None
        self._stop.clear()
        self._proc = ff.popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                              stderr=subprocess.PIPE)
        self.started_at = time.time()
        threading.Thread(target=self._feed_overlay, daemon=True).start()
        threading.Thread(target=self._watch, daemon=True).start()

    def _feed_overlay(self) -> None:
        c = self.cfg
        while not self._stop.is_set() and self.running:
            match, score = self.get_score()
            frame = overlay.render(c.width, c.height, match, score, c.logo, self.club_name)
            try:
                self._proc.stdin.write(frame)
                self._proc.stdin.flush()
            except (OSError, ValueError):
                break
            time.sleep(1 / OVERLAY_FPS)

    def _watch(self) -> None:
        stderr = self._proc.stderr.read().decode(errors="replace")
        code = self._proc.wait()
        if not self._stop.is_set():
            self.error = stderr.strip()[-300:] or f"ffmpeg s'est arrêté (code {code})"
            log.error("Terrain %s : direct interrompu : %s", self.court.id, self.error)

    def stop(self) -> None:
        self._stop.set()
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.stdin.close()
            except OSError:
                pass
            self._proc.terminate()
            try:
                self._proc.wait(5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self.started_at = None


def _double(bitrate: str) -> str:
    num = "".join(ch for ch in bitrate if ch.isdigit() or ch == ".")
    unit = bitrate[len(num):]
    return f"{float(num) * 2:g}{unit}"
