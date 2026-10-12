"""Logique du club : matchs en cours, points, temps forts, direct, ménage."""

from __future__ import annotations

import logging
import secrets
import shutil
import threading
import time
from pathlib import Path

from . import ffmpeg as ff
from .config import Config
from .db import Database
from .live import LiveStream
from .recorder import Recording, finalize
from .tennis import MatchFormat, compute

log = logging.getLogger(__name__)

MATCH_VIDEO = "match.mp4"


class ClubError(Exception):
    """Erreur à afficher telle quelle à l'utilisateur."""


class Club:
    def __init__(self, cfg: Config, db: Database | None = None):
        self.cfg = cfg
        self.db = db or Database(cfg.data_dir / "spash.db")
        self.ffmpeg = ff.find_ffmpeg(cfg)
        self.recordings: dict[str, Recording] = {}
        self.active: dict[str, int] = {}  # terrain -> id du match en cours
        self.lives: dict[str, LiveStream] = {}
        self._clip_threads: dict[int, list[threading.Thread]] = {}
        self._lock = threading.RLock()
        self._ensure_court_keys()
        self._recover()

    # --- chemins ------------------------------------------------------------
    def match_dir(self, match_id: int) -> Path:
        return self.cfg.data_dir / "matches" / str(match_id)

    def match_video(self, match: dict) -> Path:
        return self.match_dir(match["id"]) / MATCH_VIDEO

    def clip_path(self, clip: dict) -> Path:
        return self.match_dir(clip["match_id"]) / "clips" / f"clip_{clip['id']}.mp4"

    # --- clés des terrains --------------------------------------------------
    def _ensure_court_keys(self) -> None:
        for court in self.cfg.courts:
            if not self.db.get_setting(f"court_key:{court.id}"):
                self.db.set_setting(f"court_key:{court.id}", secrets.token_urlsafe(9))

    def court_key(self, court_id: str) -> str:
        return self.db.get_setting(f"court_key:{court_id}") or ""

    def check_court_key(self, court_id: str, key: str) -> bool:
        expected = self.court_key(court_id)
        return bool(expected) and secrets.compare_digest(expected, key or "")

    def rotate_court_key(self, court_id: str) -> str:
        key = secrets.token_urlsafe(9)
        self.db.set_setting(f"court_key:{court_id}", key)
        return key

    # --- reprise après un redémarrage du PC -----------------------------------
    def _recover(self) -> None:
        for match in self.db.matches_with_status("recording", "processing"):
            log.warning("Match %s interrompu (redémarrage) : assemblage de la vidéo", match["id"])
            self.db.update_match(match["id"], status="processing", ended_at=match["ended_at"] or time.time())
            threading.Thread(target=self._finalize, args=(match["id"],), daemon=True).start()

    # --- matchs -------------------------------------------------------------
    def _court(self, court_id: str):
        court = self.cfg.court(court_id)
        if not court:
            raise ClubError("Terrain inconnu.")
        return court

    def current_match(self, court_id: str) -> dict | None:
        match_id = self.active.get(court_id)
        return self.db.get_match(match_id) if match_id else None

    def start_match(self, court_id: str, team_a: str, team_b: str, fmt: dict,
                    first_server: int = 0) -> dict:
        court = self._court(court_id)
        try:
            match_format = MatchFormat.from_dict(fmt)
        except (TypeError, ValueError) as exc:
            raise ClubError(f"Format de match invalide : {exc}") from exc
        with self._lock:
            if court_id in self.active:
                raise ClubError("Un match est déjà en cours sur ce terrain.")
            match = self.db.create_match(
                token=secrets.token_urlsafe(12),
                court_id=court_id,
                team_a=(team_a or "").strip()[:40] or "Équipe A",
                team_b=(team_b or "").strip()[:40] or "Équipe B",
                format=match_format.to_dict(),
                first_server=1 if first_server else 0,
                status="recording",
                started_at=time.time(),
            )
            rec = Recording(self.ffmpeg, court, self.match_dir(match["id"]), self.cfg.segment_seconds)
            rec.start()
            if rec.video_start is None:
                rec.stop()
                error = rec.error or "La caméra ne répond pas."
                self.db.update_match(match["id"], status="error", error=error, ended_at=time.time())
                raise ClubError(f"Impossible de démarrer l'enregistrement : {error}")
            self.db.update_match(match["id"], video_start=rec.video_start)
            self.recordings[court_id] = rec
            self.active[court_id] = match["id"]
            return self.db.get_match(match["id"])

    def _require_match(self, court_id: str) -> dict:
        match = self.current_match(court_id)
        if not match:
            raise ClubError("Aucun match en cours sur ce terrain.")
        return match

    def add_point(self, court_id: str, team: int) -> dict:
        with self._lock:
            match = self._require_match(court_id)
            score = self.score(match)
            if score["finished"]:
                raise ClubError("Le match est terminé.")
            points = match["points"] + [{"w": 1 if team else 0, "t": round(time.time(), 2)}]
            self.db.update_match(match["id"], points=points)
            return self.db.get_match(match["id"])

    def undo_point(self, court_id: str) -> dict:
        with self._lock:
            match = self._require_match(court_id)
            if match["points"]:
                self.db.update_match(match["id"], points=match["points"][:-1])
            return self.db.get_match(match["id"])

    def score(self, match: dict, upto: float | None = None) -> dict:
        winners = [p["w"] for p in match["points"] if upto is None or p["t"] <= upto]
        return compute(winners, MatchFormat.from_dict(match["format"]), match["first_server"])

    def timeline(self, match: dict) -> list[dict]:
        """Score après chaque point, avec l'instant dans la vidéo (pour l'affichage en replay)."""
        fmt = MatchFormat.from_dict(match["format"])
        start = match["video_start"] or match["started_at"]
        out = [{"t": 0.0, "score": compute([], fmt, match["first_server"])}]
        winners: list[int] = []
        for p in match["points"]:
            winners.append(p["w"])
            out.append({"t": round(max(0.0, p["t"] - start), 2),
                        "score": compute(winners, fmt, match["first_server"])})
        return out

    def end_match(self, court_id: str) -> dict:
        with self._lock:
            match = self._require_match(court_id)
            del self.active[court_id]
            self.db.update_match(match["id"], status="processing", ended_at=time.time())
        threading.Thread(target=self._finalize, args=(match["id"],), daemon=True).start()
        return self.db.get_match(match["id"])

    def _finalize(self, match_id: int) -> None:
        match = self.db.get_match(match_id)
        rec = next((r for c, r in self.recordings.items()
                    if r.folder == self.match_dir(match_id)), None)
        if rec:
            rec.stop()
            self.recordings.pop(match["court_id"], None)
        for t in self._clip_threads.pop(match_id, []):
            t.join(90)
        try:
            duration = finalize(self.ffmpeg, self.match_dir(match_id), self.match_video(match))
            self.db.update_match(match_id, status="done", duration=duration)
            log.info("Match %s : vidéo prête", match_id)
        except Exception as exc:
            log.exception("Match %s : échec de l'assemblage", match_id)
            self.db.update_match(match_id, status="error", error=str(exc)[:300])

    # --- temps forts / replays ------------------------------------------------
    def create_clip(self, court_id: str, kind: str) -> dict:
        if kind not in ("highlight", "replay"):
            raise ClubError("Type de clip inconnu.")
        with self._lock:
            match = self._require_match(court_id)
            rec = self.recordings.get(court_id)
            if not rec or rec.video_start is None:
                raise ClubError("L'enregistrement n'est pas actif.")
            now = time.time()
            clip = self.db.create_clip(match["id"], kind, now - rec.video_start, now)
        if kind == "highlight":
            start, end = clip["t"] - self.cfg.highlight_before, clip["t"] + self.cfg.highlight_after
        else:
            start, end = clip["t"] - self.cfg.replay_seconds, clip["t"]
        thread = threading.Thread(target=self._make_clip, args=(rec, clip, max(0.0, start), end),
                                  daemon=True)
        self._clip_threads.setdefault(match["id"], []).append(thread)
        thread.start()
        return clip

    def _make_clip(self, rec: Recording, clip: dict, start: float, end: float) -> None:
        out = self.clip_path(clip)
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            rec.make_clip(start, end, out)
            self.db.update_clip(clip["id"], "ready")
        except Exception:
            log.exception("Clip %s : échec", clip["id"])
            self.db.update_clip(clip["id"], "error")

    # --- direct ---------------------------------------------------------------
    def start_live(self, court_id: str) -> None:
        court = self._court(court_id)
        if not self.cfg.live.enabled:
            raise ClubError("Aucune clé de diffusion configurée (section [direct] de config.toml).")
        with self._lock:
            live = self.lives.get(court_id)
            if live and live.running:
                raise ClubError("Le direct est déjà lancé sur ce terrain.")
            if any(l.running for l in self.lives.values()):
                raise ClubError("Un direct est déjà en cours sur un autre terrain.")

            def get_score():
                match = self.current_match(court_id)
                return (match, self.score(match)) if match else (None, None)

            live = LiveStream(self.ffmpeg, court, self.cfg.live, self.cfg.club_name, get_score)
            live.start()
            self.lives[court_id] = live

    def stop_live(self, court_id: str) -> None:
        live = self.lives.get(court_id)
        if live:
            live.stop()

    def live_status(self, court_id: str) -> dict:
        live = self.lives.get(court_id)
        return {
            "running": bool(live and live.running),
            "error": live.error if live and not live.running else None,
        }

    # --- ménage ---------------------------------------------------------------
    def delete_match(self, match_id: int) -> None:
        match = self.db.get_match(match_id)
        if not match:
            raise ClubError("Match introuvable.")
        if match["status"] in ("recording", "processing"):
            raise ClubError("Impossible de supprimer un match en cours.")
        shutil.rmtree(self.match_dir(match_id), ignore_errors=True)
        self.db.delete_match(match_id)

    def cleanup(self) -> int:
        """Supprime les matchs plus vieux que la durée de conservation."""
        if self.cfg.retention_days <= 0:
            return 0
        limit = time.time() - self.cfg.retention_days * 86400
        old = self.db.matches_older_than(limit)
        for match in old:
            self.delete_match(match["id"])
        if old:
            log.info("Ménage : %d match(s) supprimé(s)", len(old))
        return len(old)

    def disk_usage(self) -> dict:
        self.cfg.data_dir.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(self.cfg.data_dir)
        return {"total": usage.total, "used": usage.used, "free": usage.free}

    def shutdown(self) -> None:
        for live in self.lives.values():
            live.stop()
        for rec in list(self.recordings.values()):
            rec.stop()
