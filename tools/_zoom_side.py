from PIL import Image
im = Image.open("artifacts/qa/r31/weights.png")
crop = im.crop((10, 120, 260, 640))
crop = crop.resize((crop.width * 3, crop.height * 3), Image.NEAREST)
crop.save("artifacts/qa/r35/sidebar_zoom.png")
print("ok")
