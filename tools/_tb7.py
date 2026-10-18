from PIL import Image
im = Image.open("artifacts/shots/_drawtest.png").convert("RGB")
bright = sum(1 for p in im.get_flattened_data() if sum(p[:3]) > 200)
print("bright px", bright, im.size)
