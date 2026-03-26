import os
import io
import sys
import zipfile
import webview
from threading import Thread
from flask import Flask, render_template, request, send_file, flash, jsonify
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

# --- BRIDGE MEZI PYTHONEM A JS ---
class Api:
    def save_zip(self, *args):
        """Otevře systémové okno pro uložení ZIPu."""
        global last_zip_data
        if not last_zip_data:
            print("SERVER: V paměti nejsou žádná data.")
            return "Chyba"

        print("API: Otevírám dialog pro uložení souboru...")
        
        # OPRAVA: Použití webview.SAVE_DIALOG místo SAVE_FILE
        file_path = window.create_file_dialog(
            webview.SAVE_DIALOG, 
            directory=os.path.expanduser('~'), 
            save_filename='Bidli_CRM_Export.zip'
        )
        
        if file_path:
            # Zajistíme, aby soubor měl příponu .zip
            if isinstance(file_path, (list, tuple)):
                file_path = file_path[0]
            
            if not str(file_path).lower().endswith('.zip'):
                file_path = str(file_path) + '.zip'
                
            try:
                with open(file_path, 'wb') as f:
                    f.write(last_zip_data)
                print(f"API: Soubor byl úspěšně uložen do: {file_path}")
                return "Uloženo"
            except Exception as e:
                print(f"API CHYBA: {str(e)}")
                return f"Chyba: {str(e)}"
        
        print("API: Uživatel zrušil výběr složky.")
        return "Zrušeno"

def process_images(input_image_bytes):
    # AI ořez pozadí – alpha_matting odstraní šedý lem na hranách ořezu
    no_bg_output = remove(input_image_bytes, alpha_matting=True)
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
        if not files: return jsonify({"error": "Žádné soubory"}), 400

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
                        img.save(buf, format=fmt, quality=95)
                        zip_file.writestr(f"{filename_base}{suffix}", buf.getvalue())

            last_zip_data = zip_buffer.getvalue()
            print("SERVER: Ořez dokončen. Data připravena k uložení.")
            return jsonify({"status": "ready"})
            
        except Exception as e:
            print(f"CHYBA SERVERU: {str(e)}")
            return jsonify({"error": str(e)}), 500
                
    return render_template("index.html")

def run_flask():
    app.run(port=5001, debug=False, use_reloader=False)

if __name__ == "__main__":
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    api = Api()
    window = webview.create_window(
        'Bidli Foto Optimizer', 
        'http://127.0.0.1:5001', 
        js_api=api,
        width=1200,
        height=800,
        background_color='#111111'
    )
    webview.start()