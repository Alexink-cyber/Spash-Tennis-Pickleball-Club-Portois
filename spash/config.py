"""Lecture du fichier de configuration (config.toml)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Court:
    id: str
    name: str
    camera_url: str
    # Arguments ffmpeg placés avant « -i » (laisser vide pour les valeurs par défaut).
    input_args: list[str] | None = None
    # Réencoder la vidéo au lieu de la copier telle quelle (plus lourd pour le PC).
    transcode: bool = False


@dataclass
class LiveConfig:
    rtmp_url: str = "rtmp://a.rtmp.youtube.com/live2"
    stream_key: str = ""
    width: int = 1280
    height: int = 720
    fps: int = 25
    bitrate: str = "4500k"
    encoder: str = "libx264"
    logo: str = ""

    @property
    def enabled(self) -> bool:
        return bool(self.stream_key)


@dataclass
class Config:
    club_name: str = "Club de tennis"
    host: str = "0.0.0.0"
    port: int = 8000
    public_url: str = ""
    admin_password: str = "changeme"
    data_dir: Path = Path("data")
    retention_days: int = 30
    ffmpeg: str = ""
    segment_seconds: int = 2
    highlight_before: float = 25
    highlight_after: float = 3
    replay_seconds: float = 15
    courts: list[Court] = field(default_factory=list)
    live: LiveConfig = field(default_factory=LiveConfig)

    def court(self, court_id: str) -> Court | None:
        return next((c for c in self.courts if c.id == court_id), None)


def load_config(path: str | Path) -> Config:
    path = Path(path)
    with path.open("rb") as f:
        raw = tomllib.load(f)

    club = raw.get("club", {})
    server = raw.get("serveur", {})
    storage = raw.get("stockage", {})
    video = raw.get("video", {})
    live = raw.get("direct", {})

    data_dir = Path(storage.get("dossier", "data"))
    if not data_dir.is_absolute():
        data_dir = path.parent / data_dir

    courts = []
    for t in raw.get("terrains", []):
        courts.append(
            Court(
                id=str(t["id"]),
                name=t.get("nom", f"Terrain {t['id']}"),
                camera_url=t["camera_url"],
                input_args=t.get("arguments_entree"),
                transcode=bool(t.get("reencoder", False)),
            )
        )
    if not courts:
        raise ValueError("Aucun terrain défini dans la configuration ([[terrains]]).")
    if len({c.id for c in courts}) != len(courts):
        raise ValueError("Deux terrains ont le même id.")

    logo = live.get("logo", "")
    if logo and not Path(logo).is_absolute():
        logo = str(path.parent / logo)

    return Config(
        club_name=club.get("nom", "Club de tennis"),
        host=server.get("host", "0.0.0.0"),
        port=int(server.get("port", 8000)),
        public_url=server.get("url_publique", "").rstrip("/"),
        admin_password=server.get("mot_de_passe_admin", "changeme"),
        data_dir=data_dir,
        retention_days=int(storage.get("conservation_jours", 30)),
        ffmpeg=video.get("ffmpeg", ""),
        segment_seconds=int(video.get("duree_segment", 2)),
        highlight_before=float(video.get("temps_fort_avant", 25)),
        highlight_after=float(video.get("temps_fort_apres", 3)),
        replay_seconds=float(video.get("replay_secondes", 15)),
        courts=courts,
        live=LiveConfig(
            rtmp_url=live.get("url_rtmp", LiveConfig.rtmp_url).rstrip("/"),
            stream_key=live.get("cle", ""),
            width=int(live.get("largeur", 1280)),
            height=int(live.get("hauteur", 720)),
            fps=int(live.get("images_par_seconde", 25)),
            bitrate=str(live.get("debit", "4500k")),
            encoder=live.get("encodeur", "libx264"),
            logo=logo,
        ),
    )
