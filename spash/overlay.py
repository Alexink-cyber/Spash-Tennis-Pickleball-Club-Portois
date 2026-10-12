"""Bandeau de score (et logo) incrusté dans le direct."""

from __future__ import annotations

from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

BANNER_HEIGHT_RATIO = 0.13  # hauteur du bandeau par rapport à la hauteur de la vidéo

_FONT_CANDIDATES = [
    "arialbd.ttf", "arial.ttf", "segoeuib.ttf",  # Windows
    "DejaVuSans-Bold.ttf", "DejaVuSans.ttf",     # Linux
]


@lru_cache(maxsize=8)
def _font(size: int) -> ImageFont.ImageFont:
    for name in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


@lru_cache(maxsize=4)
def _logo(path: str, max_h: int) -> Image.Image | None:
    if not path:
        return None
    try:
        img = Image.open(path).convert("RGBA")
    except OSError:
        return None
    ratio = max_h / img.height
    return img.resize((max(1, int(img.width * ratio)), max_h))


def banner_size(width: int, height: int) -> tuple[int, int]:
    h = int(height * BANNER_HEIGHT_RATIO)
    return width, h - h % 2


def render(width: int, height: int, match: dict | None, score: dict | None,
           logo_path: str = "", club_name: str = "") -> bytes:
    """Image RGBA (octets bruts) de la taille donnée par banner_size()."""
    bw, bh = banner_size(width, height)
    img = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = bh // 8
    row_h = (bh - 2 * margin) // 2
    font = _font(int(row_h * 0.62))

    logo = _logo(logo_path, bh - 2 * margin)
    if logo:
        img.alpha_composite(logo, (bw - logo.width - margin, margin))

    if not match or not score:
        if club_name and not logo:
            draw.text((bw - margin, bh // 2), club_name, font=font,
                      fill=(255, 255, 255, 230), anchor="rm")
        return img.tobytes()

    names = [match["team_a"], match["team_b"]]
    name_w = int(bw * 0.24)
    cell_w = int(row_h * 1.1)
    columns = [s["games"] for s in score["sets"]]
    if not score["finished"] and not score["super_tiebreak"]:
        columns.append(score["games"])
    show_points = not score["finished"]
    total_w = margin + name_w + cell_w * len(columns) + (int(cell_w * 1.4) if show_points else 0) + margin

    x0, y0 = margin, margin
    draw.rounded_rectangle((x0, y0, x0 + total_w, y0 + 2 * row_h), radius=margin,
                           fill=(16, 32, 24, 215))
    for i in range(2):
        y = y0 + i * row_h
        cy = y + row_h // 2
        if not score["finished"] and score["server"] == i:
            r = row_h // 8
            draw.ellipse((x0 + margin - r, cy - r, x0 + margin + r, cy + r), fill=(214, 255, 61, 255))
        bold = score["finished"] and score["winner"] == i
        draw.text((x0 + 2 * margin + 4, cy), _fit(draw, names[i], font, name_w - 3 * margin),
                  font=font, fill=(255, 255, 255, 255) if bold or not score["finished"] else (190, 200, 195, 255),
                  anchor="lm")
        x = x0 + margin + name_w
        for col in columns:
            draw.text((x + cell_w // 2, cy), str(col[i]), font=font, fill=(255, 255, 255, 255), anchor="mm")
            x += cell_w
        if show_points:
            pw = int(cell_w * 1.4)
            draw.rectangle((x, y + 2, x + pw, y + row_h - 2), fill=(214, 255, 61, 235))
            draw.text((x + pw // 2, cy), score["points"][i], font=font, fill=(16, 32, 24, 255), anchor="mm")
    return img.tobytes()


def _fit(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> str:
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return text + "…"
