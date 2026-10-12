from spash.tennis import MatchFormat, compute, short_score

A, B = 0, 1


def game(team):
    return [team] * 4


def games(team, n):
    return [p for _ in range(n) for p in game(team)]


def test_points_labels():
    fmt = MatchFormat()
    assert compute([], fmt)["points"] == ["0", "0"]
    assert compute([A], fmt)["points"] == ["15", "0"]
    assert compute([A, A, B], fmt)["points"] == ["30", "15"]
    deuce = [A, A, A, B, B, B]
    assert compute(deuce, fmt)["points"] == ["40", "40"]
    assert compute(deuce + [B], fmt)["points"] == ["40", "AV"]
    assert compute(deuce + [B, A], fmt)["points"] == ["40", "40"]
    s = compute(deuce + [B, B], fmt)
    assert s["games"] == [0, 1] and s["points"] == ["0", "0"]


def test_no_ad_decisive_point():
    fmt = MatchFormat(no_ad=True)
    s = compute([A, A, A, B, B, B, B], fmt)
    assert s["games"] == [0, 1]


def test_server_alternates_each_game():
    fmt = MatchFormat()
    assert compute([], fmt, first_server=1)["server"] == 1
    assert compute(game(A), fmt, first_server=1)["server"] == 0


def test_set_won_6_4():
    fmt = MatchFormat()
    pts = games(A, 4) + games(B, 4) + games(A, 2)
    s = compute(pts, fmt)
    assert s["sets"] == [{"games": [6, 4], "tiebreak": None}]
    assert s["sets_won"] == [1, 0] and s["games"] == [0, 0]


def test_7_5_needs_two_games_margin():
    fmt = MatchFormat()
    pts = games(A, 5) + games(B, 5) + games(A, 1)
    assert compute(pts, fmt)["sets"] == []
    s = compute(pts + games(A, 1), fmt)
    assert s["sets"][0]["games"] == [7, 5]


def test_tiebreak_and_serve_rotation():
    fmt = MatchFormat()
    pts = games(A, 5) + games(B, 5) + games(A, 1) + games(B, 1)
    s = compute(pts, fmt, first_server=0)
    assert s["tiebreak"] and s["games"] == [6, 6]
    first = s["server"]
    # 1er point : first sert, puis l'autre sert 2 points, puis first 2 points.
    assert compute(pts + [A], fmt)["server"] == 1 - first
    assert compute(pts + [A, A], fmt)["server"] == 1 - first
    assert compute(pts + [A, A, A], fmt)["server"] == first
    s = compute(pts + [B] * 6 + [A] * 7, fmt)
    assert s["points"] == ["7", "6"] and s["tiebreak"]
    s = compute(pts + [B] * 6 + [A] * 8, fmt)
    assert s["sets"][0] == {"games": [7, 6], "tiebreak": [8, 6]}
    # Le receveur du premier point du tie-break sert le set suivant.
    assert s["server"] == 1 - first and not s["tiebreak"]


def test_match_won_and_points_after_ignored():
    fmt = MatchFormat()
    pts = games(A, 12)
    s = compute(pts, fmt)
    assert s["finished"] and s["winner"] == A and s["sets_won"] == [2, 0]
    assert compute(pts + [B, B], fmt)["sets_won"] == [2, 0]


def test_super_tiebreak_decider():
    fmt = MatchFormat(super_tiebreak=True)
    pts = games(A, 6) + games(B, 6)
    s = compute(pts, fmt)
    assert s["super_tiebreak"] and s["tiebreak"]
    s = compute(pts + [A] * 9, fmt)
    assert not s["finished"] and s["points"] == ["9", "0"]
    s = compute(pts + [A] * 10, fmt)
    assert s["finished"] and s["winner"] == A
    assert s["sets"][2] == {"games": [1, 0], "tiebreak": [10, 0]}


def test_short_sets_and_one_set():
    fmt = MatchFormat(sets_to_win=1, games_per_set=4)
    s = compute(games(B, 4), fmt)
    assert s["finished"] and s["winner"] == B


def test_short_score():
    fmt = MatchFormat()
    s = compute(games(A, 6) + games(B, 2) + [A, A], fmt)
    assert short_score(s) == "6-0 0-2 (30-0)"


def test_format_validation():
    import pytest

    with pytest.raises(ValueError):
        MatchFormat.from_dict({"sets_to_win": 5})
    assert MatchFormat.from_dict({"no_ad": True}).no_ad
