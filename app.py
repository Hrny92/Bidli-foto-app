import os
import io
import sys
import zipfile
import webbrowser
import traceback
from threading import Thread, Timer
from flask import Flask, render_template, request, send_file, jsonify
from rembg import remove
from PIL import Image

# --- NASTAVENÍ CEST PRO BALENOU APLIKACI ---
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__,
            template_folder=os.path.join(base_path, 'templates'),
            static_folder=os.path.join(base_path, 'static'))

app.secret_key = "bidli_photo_optimizer_2026"

# Globální proměnná pro ZIP data v paměti
last_zip_data = None

def process_images(input_image_bytes):
    # AI ořez pozadí – zkusíme alpha_matting, při chybě fallback
    try:
        no_bg_output = remove(input_image_bytes, alpha_matting=True)
    except Exception:
        no_bg_output = remove(input_image_bytes, alpha_matting=False)
    no_bg_image = Image.open(io.BytesIO(no_bg_output))

    def resize_and_center(img, target_size, transparent=True):
        bbox = img.getbbox()
        if bbox:
            img = img.crop(bbox)
        img.thumbnail((target_size[0], target_size[1]), Image.LANCZOS)

        new_img = Image.new("RGBA" if transparent else "RGB", target_size, (0, 0, 0, 0) if transparent else (255, 255, 255))
        offset = ((target_size[0] - img.size[0]) // 2, (target_size[1] - img.size[1]) // 2)

        if transparent:
            new_img.paste(img, offset, img)
        else:
            mask = img.split()[3] if len(img.split()) == 4 else None
            new_img.paste(img, offset, mask=mask)
        return new_img

    # Formáty Bidli CRM
    img_1980 = resize_and_center(no_bg_image, (1980, 1980), transparent=True)
    img_1000 = resize_and_center(no_bg_image, (1000, 1000), transparent=True)
    img_150 = resize_and_center(no_bg_image, (150, 200), transparent=False)

    return img_1980, img_1000, img_150

@app.route("/", methods=["GET", "POST"])
def index():
    global last_zip_data
    if request.method == "POST":
        files = request.files.getlist("photo")
        if not files:
            return jsonify({"error": "Žádné soubory"}), 400

        try:
            print(f"SERVER: Začínám zpracovávat {len(files)} fotek...")
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zip_file:
                for file in files:
                    filename_base = os.path.splitext(file.filename)[0]
                    img_1980, img_1000, img_150 = process_images(file.read())

                    for img, suffix, fmt in [(img_1980, "-1980x1980.png", "PNG"),
                                           (img_1000, "-1000x1000.png", "PNG"),
                                           (img_150, "-150x200.jpg", "JPEG")]:
                        buf = io.BytesIO()
                        if fmt == "JPEG":
                            img.save(buf, format=fmt, quality=95)
                        else:
                            img.save(buf, format=fmt)
                        zip_file.writestr(f"{filename_base}{suffix}", buf.getvalue())

            last_zip_data = zip_buffer.getvalue()
            print("SERVER: Ořez dokončen. Data připravena ke stažení.")
            return jsonify({"status": "ready"})

        except Exception as e:
            tb = traceback.format_exc()
            print(f"CHYBA SERVERU: {tb}")
            return jsonify({"error": str(e), "traceback": tb}), 500

    return render_template("index.html")

@app.route("/download")
def download():
    global last_zip_data
    if not last_zip_data:
        return jsonify({"error": "Žádná data ke stažení"}), 400
    return send_file(
        io.BytesIO(last_zip_data),
        mimetype='application/zip',
        as_attachment=True,
        download_name='Bidli_CRM_Export.zip'
    )

def open_browser():
    webbrowser.open('http://127.0.0.1:5001')

if __name__ == "__main__":
    # Otevřít prohlížeč po 1.5 sekundě (Flask potřebuje čas na start)
    Timer(1.5, open_browser).start()
    app.run(port=5001, debug=False, use_reloader=False)
