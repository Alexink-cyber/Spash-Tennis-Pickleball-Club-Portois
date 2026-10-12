"""Calcul du score de tennis.

Le score n'est jamais stocké directement : on garde la liste des points
(quelle équipe a gagné chaque point) et on recalcule tout à partir d'elle.
Annuler un point revient donc simplement à retirer le dernier élément.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

POINT_LABELS = ["0", "15", "30", "40"]


@dataclass
class MatchFormat:
    sets_to_win: int = 2          # 1 = un set, 2 = deux sets gagnants, 3 = trois sets gagnants
    games_per_set: int = 6        # 6 (classique) ou 4 (sets courts)
    no_ad: bool = False           # point décisif à 40-40
    super_tiebreak: bool = False  # set décisif remplacé par un super tie-break en 10 points

    @classmethod
    def from_dict(cls, data: dict | None) -> "MatchFormat":
        data = data or {}
        fmt = cls(
            sets_to_win=int(data.get("sets_to_win", 2)),
            games_per_set=int(data.get("games_per_set", 6)),
            no_ad=bool(data.get("no_ad", False)),
            super_tiebreak=bool(data.get("super_tiebreak", False)),
        )
        if fmt.sets_to_win not in (1, 2, 3):
            raise ValueError("sets_to_win doit valoir 1, 2 ou 3")
        if fmt.games_per_set not in (4, 6):
            raise ValueError("games_per_set doit valoir 4 ou 6")
        return fmt

    def to_dict(self) -> dict:
        return asdict(self)

    def describe(self) -> str:
        parts = {1: "1 set", 2: "2 sets gagnants", 3: "3 sets gagnants"}[self.sets_to_win]
        if self.games_per_set == 4:
            parts += " (sets en 4 jeux)"
        if self.super_tiebreak and self.sets_to_win > 1:
            parts += ", super tie-break au set décisif"
        if self.no_ad:
            parts += ", point décisif"
        return parts


def compute(points: list[int], fmt: MatchFormat, first_server: int = 0) -> dict:
    """Rejoue la liste des points et renvoie l'état complet du score."""
    sets: list[dict] = []          # sets terminés : {"games": [a, b], "tiebreak": [a, b] | None}
    sets_won = [0, 0]
    games = [0, 0]
    pts = [0, 0]
    server = first_server
    tiebreak = False
    super_tb = False
    tb_first_server = server
    winner = None

    def start_set() -> None:
        nonlocal tiebreak, super_tb, tb_first_server
        decisive = sets_won[0] == sets_won[1] == fmt.sets_to_win - 1
        if fmt.super_tiebreak and fmt.sets_to_win > 1 and decisive:
            tiebreak, super_tb, tb_first_server = True, True, server
        else:
            tiebreak, super_tb = False, False

    def finish_set(team: int, tb_points: list[int] | None) -> None:
        nonlocal games, pts, winner
        sets.append({"games": games[:], "tiebreak": tb_points})
        sets_won[team] += 1
        games, pts = [0, 0], [0, 0]
        if sets_won[team] == fmt.sets_to_win:
            winner = team
        else:
            start_set()

    start_set()
    for team in points:
        if winner is not None:
            break
        other = 1 - team
        pts[team] += 1
        if tiebreak:
            target = 10 if super_tb else 7
            if pts[team] >= target and pts[team] - pts[other] >= 2:
                tb_points = pts[:]
                games[team] += 1
                # Après un tie-break, celui qui a reçu en premier sert le set suivant.
                server = 1 - tb_first_server
                finish_set(team, tb_points)
            else:
                # Service : 1 point, puis alternance tous les 2 points.
                total = pts[0] + pts[1]
                server = tb_first_server if ((total + 1) // 2) % 2 == 0 else 1 - tb_first_server
            continue

        if pts[team] >= 4 and (fmt.no_ad or pts[team] - pts[other] >= 2):
            games[team] += 1
            pts = [0, 0]
            server = 1 - server
            n = fmt.games_per_set
            if games[team] >= n and games[team] - games[other] >= 2:
                finish_set(team, None)
            elif games[0] == games[1] == n:
                tiebreak, super_tb, tb_first_server = True, False, server

    return {
        "sets": sets,
        "sets_won": sets_won,
        "games": games,
        "points": _point_labels(pts, tiebreak, fmt.no_ad),
        "tiebreak": tiebreak,
        "super_tiebreak": super_tb,
        "server": server,
        "finished": winner is not None,
        "winner": winner,
        "points_played": len(points),
    }


def _point_labels(pts: list[int], tiebreak: bool, no_ad: bool) -> list[str]:
    if tiebreak:
        return [str(pts[0]), str(pts[1])]
    a, b = pts
    if a >= 3 and b >= 3:
        if a == b or no_ad:
            return ["40", "40"]
        return ["AV", "40"] if a > b else ["40", "AV"]
    return [POINT_LABELS[a], POINT_LABELS[b]]


def short_score(state: dict) -> str:
    """Score lisible sur une ligne, ex. « 6-4 3-6 2-1 (30-15) »."""
    parts = []
    for s in state["sets"]:
        txt = f"{s['games'][0]}-{s['games'][1]}"
        if s["tiebreak"]:
            txt += f"({min(s['tiebreak'])})"
        parts.append(txt)
    if not state["finished"]:
        if state["super_tiebreak"]:
            parts.append(f"[{state['points'][0]}-{state['points'][1]}]")
        else:
            parts.append(f"{state['games'][0]}-{state['games'][1]}")
            parts.append(f"({state['points'][0]}-{state['points'][1]})")
    return " ".join(parts)
