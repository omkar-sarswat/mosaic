"""Generate the rubber-stamp ink mask used on the brochure's stamps and seal.

Procedural alpha mask: uneven ink take-up (low-frequency), dry speckles where the rubber missed the paper, and a few
pale scuffs. Applied through CSS mask-image so every stamp prints with the slight breakage of a real impression.
Deterministic (fixed seed).
"""
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

S = 640
random.seed(20261022)

# uneven ink take-up: alpha between ~175 and 255
take = Image.effect_noise((S // 20, S // 20), 40).resize((S, S), Image.BICUBIC).filter(ImageFilter.GaussianBlur(14))
alpha = take.point(lambda v: int(max(175, min(255, 150 + v * 0.75))))

# dry speckles and scuffs
d = ImageDraw.Draw(alpha)
for _ in range(2600):
    x, y, r = random.uniform(0, S), random.uniform(0, S), random.uniform(0.4, 1.6)
    d.ellipse([x - r, y - r, x + r, y + r], fill=random.randint(0, 90))
for _ in range(26):
    x, y = random.uniform(0, S), random.uniform(0, S)
    d.line([(x, y), (x + random.uniform(-40, 40), y + random.uniform(-6, 6))], fill=random.randint(70, 140), width=2)
alpha = alpha.filter(ImageFilter.GaussianBlur(0.5))

out = Path(__file__).resolve().parent / "brand" / "ink-grain.png"
img = Image.new("RGBA", (S, S), (255, 255, 255, 255))
img.putalpha(alpha)
img.save(out, optimize=True)
print("wrote", out, out.stat().st_size // 1024, "KB")
