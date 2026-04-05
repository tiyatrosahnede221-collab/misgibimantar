import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
import tensorflow as tf
import numpy as np
from PIL import Image

# --- SİSTEM VE PERFORMANS AYARLARI ---
# TensorFlow'un gereksiz bellek tüketmesini engeller
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' 
os.environ['TENSORFLOW_INTEROP_PARALLELISM_THREADS'] = '1'
os.environ['TENSORFLOW_INTRAOP_PARALLELISM_THREADS'] = '1'

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "izmir_misaki_milli_2026_x")

# Klasör ve Dosya Yolları (Render Uyumluluğu)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "mantar_verisi.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "fotolar")
MODEL_PATH = os.path.join(BASE_DIR, "model_unquant.tflite")
LABEL_PATH = os.path.join(BASE_DIR, "labels.txt")

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- VERİTABANI BAŞLATMA ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Kullanıcılar Tablosu
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        username TEXT UNIQUE, 
        password TEXT)""")
    # Tahmin Geçmişi Tablosu
    c.execute("""CREATE TABLE IF NOT EXISTS fotolar (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        kullanici TEXT, 
        dosya_yolu TEXT, 
        sonuc TEXT, 
        yuzde REAL, 
        zaman TEXT)""")
    conn.commit()
    conn.close()

init_db()

# --- YAPAY ZEKA MOTORU (LAZY LOADING) ---
# Modeli globalde tanımlıyoruz ama fonksiyon çağrılana kadar yüklemiyoruz
interpreter = None
labels = []

def get_model_and_labels():
    global interpreter, labels
    if interpreter is None:
        if os.path.exists(MODEL_PATH) and os.path.exists(LABEL_PATH):
            interpreter = tf.lite.Interpreter(model_path=MODEL_PATH)
            interpreter.allocate_tensors()
            with open(LABEL_PATH, "r", encoding="utf-8") as f:
                labels = [line.strip() for line in f.readlines()]
        else:
            print("HATA: Model veya labels.txt bulunamadı!")
    return interpreter, labels

def tahmin_et(img_path):
    interp, lbls = get_model_and_labels()
    if interp is None: return "Sistem Hatası", 0
    
    # Görsel Hazırlama (Teachable Machine Standartları)
    img = Image.open(img_path).convert("RGB").resize((224, 224))
    img_array = np.array(img, dtype=np.float32) / 255.0
    img_array = np.expand_dims(img_array, axis=0)

    # Modeli Çalıştır
    input_details = interp.get_input_details()
    output_details = interp.get_output_details()
    interp.set_tensor(input_details[0]['index'], img_array)
    interp.invoke()
    
    # Sonucu Al
    predictions = interp.get_tensor(output_details[0]['index'])[0]
    best_idx = np.argmax(predictions)
    return lbls[best_idx], round(float(predictions[best_idx]) * 100, 2)

# --- SAYFA YÖNLENDİRMELERİ ---

@app.route("/")
def home():
    if "username" in session:
        return redirect(url_for("index"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username")
        p = request.form.get("password")
        conn = sqlite3.connect(DB_PATH)
        user = conn.execute("SELECT * FROM users WHERE username=? AND password=?", (u, p)).fetchone()
        conn.close()
        if user:
            session["username"] = u
            return redirect(url_for("index"))
        return render_template("login.html", hata="Kullanıcı adı veya şifre yanlış!")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        u = request.form.get("username")
        p = request.form.get("password")
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (u, p))
            conn.commit()
            conn.close()
            return redirect(url_for("login"))
        except:
            return render_template("register.html", hata="Bu kullanıcı adı zaten alınmış.")
    return render_template("register.html")

@app.route("/index")
def index():
    if "username" not in session: return redirect(url_for("login"))
    return render_template("index.html", username=session["username"])

@app.route("/tahmin", methods=["POST"])
def tahmin():
    if "username" not in session: return redirect(url_for("login"))
    file = request.files.get("foto")
    if file and file.filename != '':
        # Dosyayı Kaydet
        filename = f"{session['username']}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
        save_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(save_path)
        
        # Tahmin Yap
        sonuc_metni, olasilik = tahmin_et(save_path)
        
        # Veritabanına Yaz
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO fotolar (kullanici, dosya_yolu, sonuc, yuzde, zaman) VALUES (?, ?, ?, ?, ?)", 
                     (session["username"], filename, sonuc_metni, olasilik, datetime.now().strftime("%d-%m-%Y %H:%M")))
        conn.commit()
        conn.close()
        
        return render_template("index.html", sonuc=sonuc_metni, yuzde=olasilik, username=session["username"])
    return redirect(url_for("index"))

@app.route("/fotolarim")
def fotolarim():
    if "username" not in session: return redirect(url_for("login"))
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT dosya_yolu, sonuc, yuzde, zaman FROM fotolar WHERE kullanici=? ORDER BY id DESC", (session["username"],)).fetchall()
    conn.close()
    return render_template("fotolarim.html", fotolar=rows, username=session["username"])

@app.route("/yuklemeler/<filename>")
def serve_foto(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    # Render Port Ayarı
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
