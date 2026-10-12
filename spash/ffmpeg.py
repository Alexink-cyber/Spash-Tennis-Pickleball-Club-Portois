"""Petits utilitaires autour de ffmpeg."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from .config import Config, Court

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def find_ffmpeg(cfg: Config) -> str:
    """ffmpeg indiqué dans la config, sinon celui du PATH, sinon celui fourni par imageio-ffmpeg."""
    if cfg.ffmpeg:
        return cfg.ffmpeg
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover - dépend de l'installation
        raise RuntimeError(
            "ffmpeg introuvable : installez-le ou lancez « pip install imageio-ffmpeg »."
        ) from exc


def camera_input_args(court: Court) -> list[str]:
    if court.input_args is not None:
        args = list(court.input_args)
    elif court.camera_url.startswith("rtsp://"):
        # TCP est plus fiable que UDP sur la plupart des réseaux ; timeout de 10 s.
        args = ["-rtsp_transport", "tcp", "-timeout", "10000000"]
    else:
        args = []
    return args + ["-i", court.camera_url]


def video_codec_args(court: Court) -> list[str]:
    if not court.transcode:
        return ["-c:v", "copy"]
    # Une image clé par seconde : des découpes de temps forts plus précises.
    return [
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-force_key_frames", "expr:gte(t,n_forced*1)",
    ]


def popen(cmd: list[str], **kwargs) -> subprocess.Popen:
    return subprocess.Popen(cmd, creationflags=_NO_WINDOW, **kwargs)


def run(cmd: list[str], timeout: float = 600) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, timeout=timeout, creationflags=_NO_WINDOW
    )


def concat(ffmpeg: str, parts: list[Path], output: Path) -> None:
    """Assemble des segments vidéo sans réencodage."""
    if not parts:
        raise ValueError("aucun segment à assembler")
    list_file = output.with_suffix(".txt")
    lines = []
    for p in parts:
        escaped = str(p.resolve()).replace("\\", "/").replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp = output.with_name(output.stem + ".tmp" + output.suffix)
    try:
        res = run([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-c", "copy", "-movflags", "+faststart", str(tmp),
        ])
        if res.returncode != 0:
            raise RuntimeError(res.stderr.decode(errors="replace")[-500:])
        tmp.replace(output)
    finally:
        list_file.unlink(missing_ok=True)
        tmp.unlink(missing_ok=True)


def snapshot(ffmpeg: str, court: Court) -> bytes:
    """Une image JPEG de la caméra (pour tester la configuration)."""
    res = run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", *camera_input_args(court),
         "-frames:v", "1", "-f", "image2pipe", "-c:v", "mjpeg", "-"],
        timeout=20,
    )
    if res.returncode != 0 or not res.stdout:
        raise RuntimeError(res.stderr.decode(errors="replace")[-500:] or "aucune image reçue")
    return res.stdout
