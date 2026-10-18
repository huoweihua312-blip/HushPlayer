from PIL import Image, ImageDraw
from pathlib import Path
frames = sorted(Path("artifacts/rec/f1").glob("*.jpg"))
cols, rows = 4, 3
per = cols*rows
out = Path("artifacts/rec/sheets"); out.mkdir(parents=True, exist_ok=True)
thumb_w = 480
for i in range(0, len(frames), per):
    batch = frames[i:i+per]
    ims = [Image.open(p) for p in batch]
    th = int(ims[0].height * thumb_w / ims[0].width)
    sheet = Image.new("RGB", (cols*thumb_w, rows*(th+18)), (18,18,20))
    d = ImageDraw.Draw(sheet)
    for j, (p, im) in enumerate(zip(batch, ims)):
        im = im.resize((thumb_w, th), Image.LANCZOS)
        x, y = (j % cols)*thumb_w, (j//cols)*(th+18)
        sheet.paste(im, (x, y))
        d.text((x+4, y+th+3), f"{p.stem}  t={int(p.stem)-1}s", fill=(240,240,240))
    sheet.save(out / f"sheet_{i//per+1:02d}.jpg", quality=88)
print("sheets", len(list(out.glob("*.jpg"))))
