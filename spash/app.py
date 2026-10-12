"""Serveur web : pages joueurs, page gérant et API."""

from __future__ import annotations

import asyncio
import io
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

import segno
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import ffmpeg as ff
from .club import Club, ClubError
from .tennis import MatchFormat, short_score

STATIC = Path(__file__).parent / "static"


class StartMatch(BaseModel):
    team_a: str = ""
    team_b: str = ""
    sets_to_win: int = 2
    games_per_set: int = 6
    no_ad: bool = False
    super_tiebreak: bool = False
    first_server: int = Field(0, ge=0, le=1)


class Point(BaseModel):
    team: int = Field(ge=0, le=1)


class Clip(BaseModel):
    kind: str = "highlight"


def create_app(club: Club) -> FastAPI:
    cfg = club.cfg
    security = HTTPBasic(realm="Spash admin")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async def housekeeping():
            while True:
                await run_in_threadpool(club.cleanup)
                await asyncio.sleep(6 * 3600)

        task = asyncio.create_task(housekeeping())
        yield
        task.cancel()
        club.shutdown()

    app = FastAPI(title="Spash Club", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    def admin(credentials: HTTPBasicCredentials = Depends(security)) -> None:
        ok = secrets.compare_digest(credentials.password.encode(), cfg.admin_password.encode())
        if not ok:
            raise HTTPException(401, "Mot de passe incorrect",
                                headers={"WWW-Authenticate": 'Basic realm="Spash admin"'})

    def court_access(court_id: str, k: str = "") -> str:
        if not cfg.court(court_id):
            raise HTTPException(404, "Terrain inconnu")
        if not club.check_court_key(court_id, k):
            raise HTTPException(403, "Lien du terrain invalide : scannez le QR code du terrain.")
        return court_id

    def base_url(request: Request) -> str:
        return cfg.public_url or str(request.base_url).rstrip("/")

    def match_by_token(token: str) -> dict:
        match = club.db.get_match_by_token(token)
        if not match:
            raise HTTPException(404, "Match introuvable (il a peut-être été supprimé).")
        return match

    def clip_json(clip: dict, token: str) -> dict:
        return {
            "id": clip["id"],
            "kind": clip["kind"],
            "t": round(clip["t"], 1),
            "status": clip["status"],
            "url": f"/media/{token}/clips/{clip['id']}.mp4" if clip["status"] == "ready" else None,
        }

    def match_json(match: dict, request: Request, with_timeline: bool = False) -> dict:
        score = club.score(match)
        data = {
            "token": match["token"],
            "court": {"id": match["court_id"], "name": getattr(cfg.court(match["court_id"]), "name", "")},
            "team_a": match["team_a"],
            "team_b": match["team_b"],
            "format": MatchFormat.from_dict(match["format"]).describe(),
            "status": match["status"],
            "error": match["error"],
            "started_at": match["started_at"],
            "ended_at": match["ended_at"],
            "duration": match["duration"],
            "score": score,
            "score_text": short_score(score),
            "can_undo": bool(match["points"]),
            "url": f"{base_url(request)}/m/{match['token']}",
            "video_url": f"/media/{match['token']}/match.mp4" if match["status"] == "done" else None,
            "clips": [clip_json(c, match["token"]) for c in club.db.clips_for_match(match["id"])],
        }
        if with_timeline:
            data["timeline"] = [{"t": e["t"], "score": e["score"]} for e in club.timeline(match)]
        return data

    def guard(fn, *args):
        try:
            return fn(*args)
        except ClubError as exc:
            raise HTTPException(409, str(exc)) from exc

    def qr_svg(url: str) -> Response:
        buf = io.BytesIO()
        # SVG complet (avec xmlns) : utilisable en <img> comme dans la page.
        segno.make(url, error="m").save(buf, kind="svg", scale=8, border=2, xmldecl=False)
        return Response(buf.getvalue(), media_type="image/svg+xml")

    # --- pages ------------------------------------------------------------------
    def page(name: str) -> FileResponse:
        return FileResponse(STATIC / name, headers={"Cache-Control": "no-cache"})

    @app.get("/", include_in_schema=False)
    def home():
        return page("index.html")

    @app.get("/c/{court_id}", include_in_schema=False)
    def court_page(court_id: str):
        if not cfg.court(court_id):
            raise HTTPException(404, "Terrain inconnu")
        return page("court.html")

    @app.get("/m/{token}", include_in_schema=False)
    def match_page(token: str):
        match_by_token(token)
        return page("match.html")

    @app.get("/admin", include_in_schema=False, dependencies=[Depends(admin)])
    def admin_page():
        return page("admin.html")

    # --- API terrain (lien du QR code) -------------------------------------------
    @app.get("/api/info")
    def info():
        return {"club": cfg.club_name}

    @app.get("/api/courts/{court_id}")
    def court_state(request: Request, court_id: str = Depends(court_access)):
        court = cfg.court(court_id)
        match = club.current_match(court_id)
        rec = club.recordings.get(court_id)
        return {
            "club": cfg.club_name,
            "court": {"id": court.id, "name": court.name},
            "live": club.live_status(court_id)["running"],
            "recording_error": rec.error if rec and not rec.running else None,
            "match": match_json(match, request) if match else None,
            "settings": {
                "highlight_seconds": cfg.highlight_before + cfg.highlight_after,
                "replay_seconds": cfg.replay_seconds,
            },
        }

    @app.post("/api/courts/{court_id}/start")
    async def start(body: StartMatch, request: Request, court_id: str = Depends(court_access)):
        fmt = body.model_dump(include={"sets_to_win", "games_per_set", "no_ad", "super_tiebreak"})
        match = await run_in_threadpool(guard, club.start_match, court_id, body.team_a,
                                        body.team_b, fmt, body.first_server)
        return match_json(match, request)

    @app.post("/api/courts/{court_id}/point")
    def point(body: Point, request: Request, court_id: str = Depends(court_access)):
        return match_json(guard(club.add_point, court_id, body.team), request)

    @app.post("/api/courts/{court_id}/undo")
    def undo(request: Request, court_id: str = Depends(court_access)):
        return match_json(guard(club.undo_point, court_id), request)

    @app.post("/api/courts/{court_id}/clip")
    def clip(body: Clip, court_id: str = Depends(court_access)):
        match = guard(club._require_match, court_id)
        return clip_json(guard(club.create_clip, court_id, body.kind), match["token"])

    @app.post("/api/courts/{court_id}/end")
    def end(request: Request, court_id: str = Depends(court_access)):
        return match_json(guard(club.end_match, court_id), request)

    # --- API match (lien personnel des joueurs) ----------------------------------
    @app.get("/api/matches/{token}")
    def match_info(token: str, request: Request):
        return match_json(match_by_token(token), request, with_timeline=True)

    @app.get("/api/matches/{token}/qr.svg")
    def match_qr(token: str, request: Request):
        match_by_token(token)
        return qr_svg(f"{base_url(request)}/m/{token}")

    @app.get("/media/{token}/match.mp4")
    def match_video(token: str):
        match = match_by_token(token)
        path = club.match_video(match)
        if match["status"] != "done" or not path.exists():
            raise HTTPException(404, "Vidéo pas encore prête")
        return FileResponse(path, media_type="video/mp4",
                            filename=f"match-{match['started_at']:.0f}.mp4",
                            content_disposition_type="inline")

    @app.get("/media/{token}/clips/{clip_id}.mp4")
    def clip_video(token: str, clip_id: int):
        match = match_by_token(token)
        clip = club.db.get_clip(clip_id)
        if not clip or clip["match_id"] != match["id"] or clip["status"] != "ready":
            raise HTTPException(404, "Clip introuvable")
        return FileResponse(club.clip_path(clip), media_type="video/mp4",
                            filename=f"temps-fort-{clip_id}.mp4", content_disposition_type="inline")

    # --- API gérant -------------------------------------------------------------
    @app.get("/api/admin/overview", dependencies=[Depends(admin)])
    def overview(request: Request):
        base = base_url(request)
        courts = []
        for c in cfg.courts:
            match = club.current_match(c.id)
            rec = club.recordings.get(c.id)
            courts.append({
                "id": c.id,
                "name": c.name,
                "url": f"{base}/c/{c.id}?k={club.court_key(c.id)}",
                "match": {"token": match["token"], "teams": f"{match['team_a']} – {match['team_b']}",
                          "score": short_score(club.score(match))} if match else None,
                "recording_error": rec.error if rec and not rec.running else None,
                "live": club.live_status(c.id),
            })
        matches = []
        for m in club.db.list_matches():
            matches.append({
                "id": m["id"], "token": m["token"], "court_id": m["court_id"],
                "teams": f"{m['team_a']} – {m['team_b']}", "status": m["status"],
                "error": m["error"], "started_at": m["started_at"], "duration": m["duration"],
                "score": short_score(club.score(m)),
                "clips": len(club.db.clips_for_match(m["id"])),
            })
        return {
            "club": cfg.club_name,
            "courts": courts,
            "matches": matches,
            "disk": club.disk_usage(),
            "retention_days": cfg.retention_days,
            "live_configured": cfg.live.enabled,
            "public_url": cfg.public_url,
            "default_password": cfg.admin_password == "changeme",
        }

    @app.get("/api/admin/courts/{court_id}/qr.svg", dependencies=[Depends(admin)])
    def court_qr(court_id: str, request: Request):
        if not cfg.court(court_id):
            raise HTTPException(404, "Terrain inconnu")
        return qr_svg(f"{base_url(request)}/c/{court_id}?k={club.court_key(court_id)}")

    @app.post("/api/admin/courts/{court_id}/rotate-key", dependencies=[Depends(admin)])
    def rotate_key(court_id: str):
        if not cfg.court(court_id):
            raise HTTPException(404, "Terrain inconnu")
        club.rotate_court_key(court_id)
        return {"ok": True}

    @app.get("/api/admin/courts/{court_id}/snapshot", dependencies=[Depends(admin)])
    async def snapshot(court_id: str):
        court = cfg.court(court_id)
        if not court:
            raise HTTPException(404, "Terrain inconnu")
        try:
            jpeg = await run_in_threadpool(ff.snapshot, club.ffmpeg, court)
        except Exception as exc:
            raise HTTPException(502, f"Caméra injoignable : {exc}") from exc
        return Response(jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.post("/api/admin/courts/{court_id}/live/start", dependencies=[Depends(admin)])
    def live_start(court_id: str):
        guard(club.start_live, court_id)
        return club.live_status(court_id)

    @app.post("/api/admin/courts/{court_id}/live/stop", dependencies=[Depends(admin)])
    def live_stop(court_id: str):
        club.stop_live(court_id)
        return club.live_status(court_id)

    @app.post("/api/admin/courts/{court_id}/end", dependencies=[Depends(admin)])
    def admin_end(court_id: str, request: Request):
        return match_json(guard(club.end_match, court_id), request)

    @app.delete("/api/admin/matches/{match_id}", dependencies=[Depends(admin)])
    def delete_match(match_id: int):
        guard(club.delete_match, match_id)
        return {"ok": True}

    @app.post("/api/admin/cleanup", dependencies=[Depends(admin)])
    def cleanup():
        return {"deleted": club.cleanup()}

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return RedirectResponse("/static/favicon.svg")

    return app
