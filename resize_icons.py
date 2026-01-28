from PIL import Image
import os

sizes = [(192, 192), (512, 512)]
input_path = "frontend/public/icon.png"
output_dir = "frontend/public"

if os.path.exists(input_path):
    img = Image.open(input_path)
    for w, h in sizes:
        resized = img.resize((w, h), Image.Resampling.LANCZOS)
        resized.save(os.path.join(output_dir, f"pwa-{w}x{h}.png"))
    print("Icons generated.")
else:
    print("Input icon not found.")
