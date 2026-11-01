"""Generate the kraft file-board texture used on the brochure jacket (cover and back cover).

Procedural: a warm kraft base, low-frequency mottling, fine grain and a few thousand short fibres, as on the
board of an Indian government file jacket. Deterministic (fixed seed), A4 at 150 dpi.
"""
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

W, H = 1240, 1754
random.seed(20261022)
base = Image.new("RGB", (W, H), (164, 132, 86))

# low-frequency mottling
mott = Image.effect_noise((W // 16, H // 16), 22).resize((W, H), Image.BICUBIC).filter(ImageFilter.GaussianBlur(18))
base = Image.composite(Image.new("RGB", (W, H), (150, 118, 74)), base, mott.point(lambda v: int(max(0, v - 110) * 1.4)))

# fibres
fib = Image.new("RGBA", (W, H), (0, 0, 0, 0))
d = ImageDraw.Draw(fib)
for _ in range(9000):
    x, y = random.uniform(0, W), random.uniform(0, H)
    length = random.uniform(4, 22)
    dx, dy = random.uniform(-1, 1) * length, random.uniform(-0.35, 0.35) * length
    tone = random.choice([(120, 92, 54, 70), (196, 166, 118, 80), (138, 106, 64, 60), (210, 182, 136, 55)])
    d.line([(x, y), (x + dx, y + dy)], fill=tone, width=1)
base = Image.alpha_composite(base.convert("RGBA"), fib.filter(ImageFilter.GaussianBlur(0.4)))

# fine grain
grain = Image.effect_noise((W, H), 9).convert("L")
base = Image.composite(Image.new("RGBA", (W, H), (110, 84, 48, 255)), base, grain.point(lambda v: 26 if v > 150 else 0))
out = Path(__file__).resolve().parent / "brand" / "kraft-board.jpg"
base.convert("RGB").save(out, quality=88, optimize=True, progressive=True)
print("wrote", out, out.stat().st_size // 1024, "KB")
