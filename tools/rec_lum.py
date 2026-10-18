from PIL import Image, ImageStat
from pathlib import Path
for seg, start in (("seg_a", 69.0), ("seg_b", 84.0)):
    frames = sorted(Path(f"artifacts/rec/{seg}").glob("*.jpg"))
    vals = []
    for p in frames:
        im = Image.open(p).convert("L")
        vals.append((ImageStat.Stat(im).mean[0], p.name))
    mean_all = sum(v for v, _ in vals) / len(vals)
    print(f"== {seg} mean={mean_all:.1f}")
    for i, (v, name) in enumerate(vals):
        t = start + i / 30
        if abs(v - mean_all) > 12:
            print(f"  t={t:6.2f} lum={v:6.1f} {name}")
    # print course every 15 frames
    print("  course:", " ".join(f"{start+i/30:.1f}:{v:.0f}" for i, (v, _) in enumerate(vals) if i % 10 == 0))
