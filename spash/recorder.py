"""Enregistrement d'une caméra en petits segments.

ffmpeg copie le flux de la caméra (sans réencodage, donc très peu de
processeur) dans des fichiers de quelques secondes. Cela permet de fabriquer
un temps fort pendant le match en recollant les derniers segments, puis
d'assembler la vidéo complète à la fin.
"""

from __future__ import annotations

import csv
import logging
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import ffmpeg as ff
from .config import Court

log = logging.getLogger(__name__)

SEGMENT_LIST = "segments.csv"


@dataclass
class Segment:
    path: Path
    start: float  # secondes depuis le début de la vidéo
    end: float


def read_segments(folder: Path) -> list[Segment]:
    """Segments terminés, avec leur position dans la vidéo."""
    list_path = folder / SEGMENT_LIST
    if not list_path.exists():
        return []
    segments = []
    pos = 0.0
    with list_path.open(newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if len(row) < 3:
                continue
            try:
                duration = float(row[2]) - float(row[1])
            except ValueError:
                continue
            path = folder / row[0]
            if path.exists():
                segments.append(Segment(path, pos, pos + duration))
            pos += duration
    return segments


class Recording:
    def __init__(self, ffmpeg: str, court: Court, folder: Path, segment_seconds: int):
        self.ffmpeg = ffmpeg
        self.court = court
        self.folder = folder
        self.segment_seconds = segment_seconds
        self.video_start: float | None = None
        self.error: str | None = None
        self._proc: subprocess.Popen | None = None
        self._stopping = False
        self._started = threading.Event()

    def start(self, wait: float = 15) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        cmd = [
            self.ffmpeg, "-hide_banner", "-loglevel", "error",
            *ff.camera_input_args(self.court),
            "-map", "0:v:0", *ff.video_codec_args(self.court), "-an",
            "-f", "segment", "-segment_time", str(self.segment_seconds),
            "-segment_format", "matroska",
            "-segment_list", SEGMENT_LIST, "-segment_list_type", "csv",
            "seg_%05d.mkv",
        ]
        log.info("Terrain %s : démarrage de l'enregistrement", self.court.id)
        self._proc = ff.popen(
            cmd, cwd=self.folder, stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        threading.Thread(target=self._watch, daemon=True).start()
        self._started.wait(wait)

    def _watch(self) -> None:
        first = self.folder / "seg_00000.mkv"
        while self._proc.poll() is None and not first.exists():
            time.sleep(0.1)
        if first.exists():
            self.video_start = time.time()
            self._started.set()
        stderr = self._proc.stderr.read().decode(errors="replace") if self._proc.stderr else ""
        code = self._proc.wait()
        if code != 0 and not self._stopping:
            self.error = stderr.strip()[-300:] or f"ffmpeg s'est arrêté (code {code})"
            log.error("Terrain %s : enregistrement interrompu : %s", self.court.id, self.error)
        self._started.set()

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def stop(self) -> None:
        if not self._proc:
            return
        self._stopping = True
        if self._proc.poll() is None:
            try:
                # « q » demande à ffmpeg de finir proprement le segment en cours.
                self._proc.stdin.write(b"q")
                self._proc.stdin.flush()
            except OSError:
                pass
            try:
                self._proc.wait(15)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait()

    def segments(self) -> list[Segment]:
        return read_segments(self.folder)

    def make_clip(self, start: float, end: float, output: Path, timeout: float = 60) -> None:
        """Clip entre deux instants (en secondes depuis le début de la vidéo).

        Attend que les segments couvrant la fin du clip soient terminés.
        """
        deadline = time.time() + timeout
        while True:
            segs = self.segments()
            if (segs and segs[-1].end >= end) or not self.running or time.time() > deadline:
                break
            time.sleep(0.5)
        parts = [s.path for s in segs if s.end > start and s.start < end]
        ff.concat(self.ffmpeg, parts, output)


def finalize(ffmpeg: str, folder: Path, output: Path) -> float:
    """Assemble tous les segments en une seule vidéo, puis les supprime.

    Renvoie la durée de la vidéo en secondes.
    """
    segs = read_segments(folder)
    if not segs:
        # Segments présents mais liste absente (arrêt brutal) : on les prend dans l'ordre.
        paths = sorted(folder.glob("seg_*.mkv"))
        if not paths:
            raise RuntimeError("aucune vidéo enregistrée (caméra injoignable ?)")
        ff.concat(ffmpeg, paths, output)
        duration = 0.0
    else:
        ff.concat(ffmpeg, [s.path for s in segs], output)
        duration = segs[-1].end
    for p in folder.glob("seg_*.mkv"):
        p.unlink(missing_ok=True)
    (folder / SEGMENT_LIST).unlink(missing_ok=True)
    return duration
