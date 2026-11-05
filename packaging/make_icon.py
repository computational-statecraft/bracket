"""Draw the app icon (a pair of square brackets on near-black) and write build/icon.png, icon.icns (macOS) and
icon.ico (Windows). No font needed: the brackets are rectangles."""
from pathlib import Path

from PIL import Image, ImageDraw

S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([40, 40, S - 40, S - 40], radius=200, fill=(10, 10, 11, 255))
gold, white = (217, 196, 155, 255), (255, 255, 255, 255)
t, h, w, top = 46, 520, 120, (S - 520) // 2      # stroke, bracket height, arm width
for x0, flip in ((300, False), (S - 300, True)):
    xs = x0 - t if flip else x0
    d.rectangle([xs, top, xs + t, top + h], fill=white)
    arm = (x0 - w, x0) if flip else (x0, x0 + w)
    d.rectangle([arm[0], top, arm[1], top + t], fill=white)
    d.rectangle([arm[0], top + h - t, arm[1], top + h], fill=white)
d.rectangle([S // 2 - 110, S // 2 + 150, S // 2 + 110, S // 2 + 150 + 30], fill=gold)   # the brass rule
out = Path(__file__).resolve().parent.parent / "build" / "icon.png"
out.parent.mkdir(exist_ok=True)
img.save(out)
img.save(out.with_suffix(".icns"))
img.save(out.with_suffix(".ico"), sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("wrote", out, out.with_suffix(".icns"), out.with_suffix(".ico"))
