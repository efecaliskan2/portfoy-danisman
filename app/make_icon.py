"""
Uygulama simgesini üretir: app/icon.ico (çok boyutlu) + app/icon_preview.png
Tasarım: uygulamanın petrol/okyanus temasıyla uyumlu koyu zemin + parlayan
yeşil değer grafiği (uygulamadaki "Değer Geçmişi" kartının minyatürü).
4x süperörnekleme ile çizilir -> kenarlar pürüzsüz.
"""
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

S = 256          # nihai boyut
SS = 4           # süperörnekleme çarpanı (antialiasing için büyük çiz, küçült)
OUT = Path(__file__).resolve().parent

# Uygulama paleti (web/style.css ile uyumlu)
BG_TOP = (18, 46, 62)     # petrol — üst
BG_BOT = (7, 16, 23)      # derin gece — alt
RIM = (255, 255, 255, 26)
GRID = (255, 255, 255, 16)
GREEN = (47, 208, 138)    # --pos
DOT = (236, 253, 245)


def _vertical_gradient(size: int, top: tuple, bot: tuple) -> Image.Image:
    img = Image.new("RGB", (size, size))
    d = ImageDraw.Draw(img)
    for y in range(size):
        t = y / (size - 1)
        d.line([(0, y), (size, y)],
               fill=tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)))
    return img


def build(size: int = S) -> Image.Image:
    W = size * SS
    r = int(W * 0.22)                     # köşe yarıçapı

    # 1) Zemin: dikey petrol degrade + yuvarlak köşe maskesi
    base = _vertical_gradient(W, BG_TOP, BG_BOT)
    mask = Image.new("L", (W, W), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, W - 1, W - 1], radius=r, fill=255)
    icon = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    icon.paste(base, (0, 0), mask)
    dd = ImageDraw.Draw(icon)

    def P(fx: float, fy: float) -> tuple:
        return (fx * W, fy * W)

    # 2) Zayıf yatay kılavuz çizgileri (grafik hissi)
    #    Ayrı katman + alpha_composite: doğrudan çizim alfa KARIŞTIRMAZ, deler.
    grid = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    gdr = ImageDraw.Draw(grid)
    for fy in (0.32, 0.50, 0.68):
        gdr.line([P(0.14, fy), P(0.86, fy)], fill=GRID, width=max(1, W // 256))
    icon.alpha_composite(grid)

    # 3) Değer eğrisi noktaları (küçük bir düşüşle gerçekçi yükseliş)
    pts = [P(0.14, 0.72), P(0.32, 0.56), P(0.47, 0.62), P(0.66, 0.40), P(0.85, 0.27)]

    # 4) Eğri altı alan: yeşil -> saydam degrade
    #    (poligon maskesi x dikey alfa rampası -> alpha_composite; zemini delmez)
    area_mask = Image.new("L", (W, W), 0)
    ImageDraw.Draw(area_mask).polygon(pts + [P(0.85, 0.86), P(0.14, 0.86)], fill=255)
    ramp = Image.new("L", (W, W), 0)
    rd = ImageDraw.Draw(ramp)
    top_a = 92
    y0, y1 = int(0.27 * W), int(0.86 * W)
    for y in range(y0, y1):
        rd.line([(0, y), (W, y)], fill=int(top_a * (1 - (y - y0) / (y1 - y0))))
    fill = Image.new("RGBA", (W, W), GREEN + (255,))
    fill.putalpha(ImageChops.multiply(ramp, area_mask))
    icon.alpha_composite(fill)

    # 5) Çizginin parlaması (glow): kalın çiz, bulanıklaştır, altına ser
    glow = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.line(pts, fill=GREEN + (170,), width=int(W * 0.055), joint="curve")
    glow = glow.filter(ImageFilter.GaussianBlur(W * 0.025))
    icon.alpha_composite(glow)

    # 6) Çizginin kendisi + yumuşak uçlar
    lw = int(W * 0.042)
    dd.line(pts, fill=GREEN + (255,), width=lw, joint="curve")
    for p in (pts[0], pts[-1]):
        dd.ellipse([p[0] - lw / 2, p[1] - lw / 2, p[0] + lw / 2, p[1] + lw / 2],
                   fill=GREEN + (255,))

    # 7) Uç nokta: parlayan beyaz nokta ("şu anki değer")
    ex, ey = pts[-1]
    halo = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    hd = ImageDraw.Draw(halo)
    hr = W * 0.055
    hd.ellipse([ex - hr, ey - hr, ex + hr, ey + hr], fill=GREEN + (200,))
    halo = halo.filter(ImageFilter.GaussianBlur(W * 0.02))
    icon.alpha_composite(halo)
    dr = W * 0.026
    dd.ellipse([ex - dr, ey - dr, ex + dr, ey + dr], fill=DOT + (255,))

    # 8) İnce iç kenarlık (taskbar'da koyu zeminde okunabilirlik) — ayrı katman
    rim = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    ImageDraw.Draw(rim).rounded_rectangle([0, 0, W - 1, W - 1], radius=r,
                                          outline=RIM, width=max(2, W // 200))
    icon.alpha_composite(rim)

    return icon.resize((size, size), Image.LANCZOS)


def main():
    big = build(S)
    big.save(OUT / "icon_preview.png")
    big.save(OUT / "icon.ico",
             sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("Olusturuldu:", OUT / "icon.ico", "ve icon_preview.png")


if __name__ == "__main__":
    main()
