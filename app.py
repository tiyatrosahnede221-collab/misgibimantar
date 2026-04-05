import os
import sqlite3
import secrets
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory
import tensorflow as tf
import numpy as np
from PIL import Image

# --- 1. SİSTEM VE YOL AYARLARI (RENDER UYUMLU) ---
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
# RAM kullanımını düşük tutmak için thread sınırlandırması
os.environ['TENSORFLOW_INTEROP_PARALLELISM_THREADS'] = '1'
os.environ['TENSORFLOW_INTRAOP_PARALLELISM_THREADS'] = '1'

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "mantar_projesi_2026_guvenli_anahtar")

# Klasör ve Dosya Yolları
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "konumlar.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "fotolar")
MODEL_PATH = os.path.join(BASE_DIR, "model_unquant.tflite")
LABEL_PATH = os.path.join(BASE_DIR, "labels.txt")

# Fotoğraf klasörü yoksa oluştur
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- 2. SMTP (E-POSTA) BİLGİLERİ ---
SMTP_USER = "erkanerakman137@gmail.com"
SMTP_PASS = "nrqv nmar ciif sjgs"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# --- 3. VERİTABANI BAŞLATMA ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Kullanıcılar tablosu
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        username TEXT UNIQUE, 
        password TEXT, 
        recovery_email TEXT)""")
    # Fotoğraflar ve Tahmin Sonuçları tablosu
    c.execute("""CREATE TABLE IF NOT EXISTS fotolar (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        kullanici TEXT, 
        dosya_yolu TEXT, 
        sonuc TEXT, 
        yuzde REAL, 
        zaman TEXT)""")
    # Şifre Sıfırlama tablosu
    c.execute("""CREATE TABLE IF NOT EXISTS password_resets (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        username TEXT, 
        token TEXT UNIQUE, 
        code TEXT, 
        expires_at TEXT)""")
    conn.commit()
    conn.close()

init_db()

# --- 4. YAPAY ZEKA MODELİ YÜKLEME ---
labels = []
interpreter = None
try:
    if os.path.exists(MODEL_PATH) and os.path.exists(LABEL_PATH):
        # TFLite Modelini yükle
        interpreter = tf.lite.Interpreter(model_path=MODEL_PATH)
        interpreter.allocate_tensors()
        # Etiketleri oku
        with open(LABEL_PATH, "r", encoding="utf-8") as f:
            labels = [line.strip() for line in f.readlines()]
        print("✅ Başarılı: Model ve Etiketler yüklendi.")
    else:
        print("❌ Hata: Model veya labels.txt dosyası bulunamadı!")
except Exception as e:
    print(f"⚠️ Model yüklenirken hata oluştu: {e}")

# --- 5. TAHMİN FONKSİYONU ---
def tahmin_et(img_path):
    if interpreter is None:
        return "Model Yüklenemedi", 0
    
    # Görüntüyü hazırla (224x224 RGB ve Normalize)
    img = Image.open(img_path).convert("RGB").resize((224, 224))
    img_array = np.array(img, dtype=np.float32) / 255.0
    img_array = np.expand_dims(img_array, axis=0)

    # Modeli çalıştır
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()
    
    interpreter.set_tensor(input_details[0]['index'], img_array)
    interpreter.invoke()
    
    # En yüksek olasılığı bul
    predictions = interpreter.get_tensor(output_details[0]['index'])[0]
    best_index = np.argmax(predictions)
    confidence = round(float(predictions[best_index]) * 100, 2)
    
    return labels[best_index], confidence

# --- 6. SAYFA YÖNLENDİRMELERİ (ROUTES) ---

@app.route("/")
def home():
    if "username" in session:
        return redirect(url_for("index"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    hata = None
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=? AND password=?", (u, p))
        user = c.fetchone()
        conn.close()
        if user:
            session["username"] = u
            return redirect(url_for("index"))
        hata = "Kullanıcı adı veya şifre yanlış!"
    return render_template("login.html", hata=hata, msg=request.args.get("msg"))

@app.route("/register", methods=["GET", "POST"])
def register():
    hata = None
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]
        e = request.form.get("recovery_email")
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("INSERT INTO users (username, password, recovery_email) VALUES (?, ?, ?)", (u, p, e))
            conn.commit()
            conn.close()
            return redirect(url_for("login", msg="Kayıt başarılı! Giriş yapabilirsiniz."))
        except:
            hata = "Bu kullanıcı adı zaten alınmış."
    return render_template("register.html", hata=hata)

@app.route("/index")
def index():
    if "username" not in session: return redirect(url_for("login"))
    return render_template("index.html", username=session["username"])

@app.route("/tahmin", methods=["POST"])
def tahmin():
    if "username" not in session: return redirect(url_for("login"))
    
    file = request.files.get("foto")
    if file:
        filename = f"{session['username']}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
        save_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(save_path)
        
        # Tahmin yap
        sonuc, yuzde = tahmin_et(save_path)
        
        # Veritabanına kaydet
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO fotolar (kullanici, dosya_yolu, sonuc, yuzde, zaman) VALUES (?, ?, ?, ?, ?)", 
                 (session["username"], filename, sonuc, yuzde, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        
        return render_template("index.html", sonuc=sonuc, yuzde=yuzde, username=session["username"])
    return redirect(url_for("index"))

@app.route("/fotolarim")
def fotolarim():
    if "username" not in session: return redirect(url_for("login"))
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT dosya_yolu, sonuc, yuzde, zaman FROM fotolar WHERE kullanici=? ORDER BY id DESC", (session["username"],))
    rows = c.fetchall()
    conn.close()
    return render_template("fotolarim.html", fotolar=rows, username=session["username"])

@app.route("/fotolar/<path:filename>")
def serve_foto(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route("/forgot", methods=["GET", "POST"])
def forgot():
    info = None
    if request.method == "POST":
        u = request.form.get("username")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT recovery_email FROM users WHERE username=?", (u,))
        row = c.fetchone()
        conn.close()
        
        if row and row[0]:
            code = f"{secrets.randbelow(10**6):06d}"
            try:
                msg = EmailMessage()
                msg.set_content(f"Şifre sıfırlama kodunuz: {code}")
                msg["Subject"] = "Mantar Projesi Şifre Sıfırlama"
                msg["From"] = SMTP_USER
                msg["To"] = row[0]
                with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                    server.starttls()
                    server.login(SMTP_USER, SMTP_PASS)
                    server.send_message(msg)
                info = "Sıfırlama kodu e-postanıza gönderildi."
            except Exception as e:
                info = f"E-posta hatası! Kodunuz: {code} (Geliştirici modunda kod burada gösterilir)"
        else:
            info = "Kullanıcı veya e-posta adresi bulunamadı."
    return render_template("forgot_password.html", info=info)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    # Render için Port ayarı
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
