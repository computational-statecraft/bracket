"""Draw the app icon and the installer window's background, and write them to build/:

  icon.png, icon.icns (macOS), icon.ico (Windows)   the app icon
  dmg-background.png, dmg-background@2x.png         the Mac disk image's window (drag to Applications)

The icon: a pair of serif square brackets holding two choices, the chosen one in brass. It follows Apple's icon grid
(an 824-pixel rounded square inside a 1024 canvas, with a soft shadow), so it sits at the right size in the Dock.
Run with Pillow:  uv run --with pillow python packaging/make_icon.py
"""
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
SERIF = ROOT / "site" / "fonts" / "CormorantGaramond.woff2"
SANS = ROOT / "site" / "fonts" / "DMSans.woff2"

INK, PAPER = (10, 10, 11), (255, 255, 255)
CREAM, BRASS, BRASS_DEEP = (244, 238, 226), (205, 172, 112), (135, 103, 51)


def font(path: Path, size: int, weight: int | None = None) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(path), size)
    if weight:
        try:                                    # both fonts are variable: pick the weight
            f.set_variation_by_axes([weight])
        except Exception:  # noqa: BLE001
            pass
    return f


def vgradient(size: tuple[int, int], top: tuple, bottom: tuple) -> Image.Image:
    w, h = size
    g = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(h - 1, 1)
        g.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    return g.resize((w, h))


def icon(S: int = 1024) -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    x0, x1, r = round(S * 100 / 1024), round(S * 924 / 1024), round(S * 186 / 1024)
    body = [x0, x0, x1, x1]

    # shadow under the tile
    sh = Image.new("L", (S, S), 0)
    ImageDraw.Draw(sh).rounded_rectangle([x0, x0 + S * 12 // 1024, x1, x1 + S * 12 // 1024], r, fill=110)
    sh = sh.filter(ImageFilter.GaussianBlur(S * 18 / 1024))
    img.paste((0, 0, 0, 255), (0, 0), sh)

    # the tile: warm near-black, lighter at the top
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle(body, r, fill=255)
    img.paste(vgradient((S, S), (34, 32, 36), (11, 11, 13)), (0, 0), mask)
    rim = Image.new("L", (S, S), 0)                                     # a hairline of light along the top edge
    ImageDraw.Draw(rim).rounded_rectangle(body, r, outline=60, width=max(2, S // 340))
    rim = ImageChops.multiply(rim, vgradient((S, S), (255,) * 3, (0,) * 3).convert("L"))
    img.paste((255, 255, 255, 255), (0, 0), rim)

    d = ImageDraw.Draw(img)
    # the brackets, set in the same serif as the app
    f = font(SERIF, round(S * 0.58), 600)
    cy = S * 0.5
    for ch, cx in (("[", S * 0.315), ("]", S * 0.685)):
        d.text((cx, cy), ch, font=f, fill=CREAM, anchor="mm")
    # two choices between them: the chosen one in brass, the other waiting
    bw, bh = S * 0.24, S * 0.062
    for i, (col, w) in enumerate(((BRASS, bw), ((84, 82, 88), bw * 0.68))):
        y = cy - S * 0.068 + i * S * 0.136
        d.rounded_rectangle([S / 2 - bw / 2, y - bh / 2, S / 2 - bw / 2 + w, y + bh / 2], bh / 2, fill=col)
    return img


def dmg_background(scale: int = 1) -> Image.Image:
    """640x400 points: the app on the left, Applications on the right, an arrow between (positions match
    packaging/dmg_settings.py)."""
    W, H = 640 * scale, 400 * scale
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    d.text((W / 2, 64 * scale), "[bracket]", font=font(SERIF, 44 * scale, 500), fill=INK, anchor="mm")
    d.text((W / 2, 104 * scale), "Drag to Applications to install", font=font(SANS, 13 * scale, 500),
           fill=BRASS_DEEP, anchor="mm")
    # a slim arrow from the app (x 170) to Applications (x 470), at icon height (y 215)
    y, a, b = 215 * scale, 250 * scale, 390 * scale
    d.line([(a, y), (b, y)], fill=(200, 194, 182), width=max(1, scale + scale // 2))
    d.line([(b - 9 * scale, y - 7 * scale), (b, y), (b - 9 * scale, y + 7 * scale)], fill=(200, 194, 182),
           width=max(1, scale + scale // 2), joint="curve")
    d.text((W / 2, 352 * scale), "Open it from Applications. The first time, macOS asks you to confirm.",
           font=font(SANS, 11 * scale, 400), fill=(120, 118, 112), anchor="mm")
    return img


if __name__ == "__main__":
    BUILD.mkdir(exist_ok=True)
    big = icon(1024)
    out = BUILD / "icon.png"
    big.save(out)
    big.save(out.with_suffix(".icns"))
    # small Windows sizes are drawn from the large one; the tile already has its own margin
    big.save(out.with_suffix(".ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    dmg_background(1).save(BUILD / "dmg-background.png")
    dmg_background(2).save(BUILD / "dmg-background@2x.png")
    print("wrote", ", ".join(p.name for p in sorted(BUILD.glob("icon.*")) + sorted(BUILD.glob("dmg-background*"))))
