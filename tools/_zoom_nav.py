from PIL import Image
im = Image.open("artifacts/qa/r28/settings_150.png")
crop = im.crop((240, 170, 520, 690))
crop = crop.resize((crop.width * 3, crop.height * 3), Image.NEAREST)
crop.save("artifacts/qa/r35/nav_zoom.png")
print("ok")
