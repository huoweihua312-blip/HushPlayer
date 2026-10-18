from PIL import Image
for name in ["_closebtn.png","_closebtn2.png"]:
    im = Image.open("artifacts/shots/"+name).convert("RGBA")
    n = sum(1 for p in im.getdata() if p[3] > 20)
    print(name, im.size, "alpha_px", n)
