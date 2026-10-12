"""Lancement : python -m spash [--config config.toml]"""

from __future__ import annotations

import argparse
import logging
import socket
import sys
from pathlib import Path

import uvicorn

from .app import create_app
from .club import Club
from .config import load_config


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def main() -> None:
    parser = argparse.ArgumentParser(description="Spash Club : vidéo et score des terrains")
    parser.add_argument("--config", default="config.toml", help="fichier de configuration")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    config_path = Path(args.config)
    if not config_path.exists():
        sys.exit(f"Fichier {config_path} introuvable : copiez config.exemple.toml en config.toml.")
    cfg = load_config(config_path)
    club = Club(cfg)

    log = logging.getLogger("spash")
    if cfg.admin_password == "changeme":
        log.warning("Mot de passe gérant par défaut : changez-le dans config.toml !")
    log.info("ffmpeg : %s", club.ffmpeg)
    log.info("Page gérant : http://%s:%d/admin", local_ip(), cfg.port)

    uvicorn.run(create_app(club), host=cfg.host, port=cfg.port, log_level="warning")


if __name__ == "__main__":
    main()
