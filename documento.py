from PIL import Image
from pathlib import Path

src = Path("src/static/img/bombeiros_5.png")
out = Path("src/static/img")

sizes = [(1920,0),(1280,0),(768,0)]  # largura, altura 0 = proporcional
qualities = {1920:72, 1280:70, 768:68}

im = Image.open(src).convert("RGB")
for w,h in sizes:
    im2 = im.copy()
    if w and h==0:
        ratio = w / im2.width
        h = int(im2.height*ratio)
    im2 = im2.resize((w,h), Image.LANCZOS)
    # WebP
    im2.save(out/f"bombeiros_5_{w}.webp", format="WEBP",
             quality=qualities[w], method=6, optimize=True)
    # (Opcional) AVIF se tiver pillow-avif-plugin instalado:
    # im2.save(out/f"bombeiros_5_{w}.avif", format="AVIF", quality=qualities[w])
