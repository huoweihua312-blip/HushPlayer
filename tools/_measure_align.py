from PIL import Image
import numpy as np
a = np.asarray(Image.open("artifacts/qa/r28/settings_150.png").convert("L"))
for y in (198, 249, 300, 351, 402, 453, 504, 555, 606, 657):
    band = a[y-24:y+26, :]
    icon = band[:, 295:328]
    text = band[:, 330:480]
    iy = np.nonzero((icon > 80).sum(axis=1))[0]
    tx = np.nonzero((text > 80).sum(axis=1))[0]
    if len(iy) == 0 or len(tx) == 0:
        continue
    ic = (iy[0] + iy[-1]) / 2
    tc = (tx[0] + tx[-1]) / 2
    ix = np.nonzero((icon > 80).sum(axis=0))[0]
    txx = np.nonzero((text > 80).sum(axis=0))[0]
    print(
        "row", y,
        "icon_cy", round(ic, 1), "text_cy", round(tc, 1), "delta", round(ic - tc, 1),
        "icon_h", int(iy[-1] - iy[0] + 1), "text_h", int(tx[-1] - tx[0] + 1),
        "icon_x", int(ix[0] + 295), "icon_right", int(ix[-1] + 295),
        "text_x", int(txx[0] + 330), "gap", int(txx[0] + 330 - (ix[-1] + 295)),
    )
