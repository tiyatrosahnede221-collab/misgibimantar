import os
import sqlite3
import secrets
import smtplib
import socket
import numpy as np
from datetime import datetime, timedelta
from email.message import EmailMessage
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory
from PIL import Image

# TFLite Runtime: TensorFlow'un 500MB'lık yükünden kurtulup sadece 15MB ile çalışmamızı sağlar.
try:
    from tflite_runtime.interpreter import Interpreter
except ImportError:
    import tensorflow as tf
    Interpreter = tf.lite.Interpreter

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "mantar-projesi-gizli-anahtar-123")

# --- KLASÖR VE DOSYA AYARLARI ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "fotolar")
MODEL_PATH = os.path.join(BASE_DIR, "model_unquant.tflite")
LABEL_PATH = os.path.join(BASE_DIR, "labels.txt")
DB_PATH = os.path.join(BASE_DIR, "konumlar.db")

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- SMTP AYARLARI ---
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "erkanerakman137@gmail.com"
SMTP_PASS = "nrqv nmar ciif sjgs" # Uygulama şifresi

# --- VERİTABANI BAŞLATMA ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, recovery_email TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS konumlar (id INTEGER PRIMARY KEY AUTOINCREMENT, kullanici TEXT, konum TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS fotolar (id INTEGER PRIMARY KEY AUTOINCREMENT, kullanici TEXT, dosya_yolu TEXT, yuklenme_zamani TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS password_resets (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, token TEXT UNIQUE, code TEXT, expires_at TEXT)")
    conn.commit()
    conn.close()

init_db()

# --- MODEL YÜKLEME ---
# Sunucu başlarken modeli bir kez yükler (RAM dostu)
if os.path.exists(MODEL_PATH) and os.path.exists(LABEL_PATH):
    interpreter = Interpreter(model_path=MODEL_PATH)
    interpreter.allocate_tensors()
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()
    with open(LABEL_PATH, "r", encoding="utf-8") as f:
        labels = [line.strip() for line in f.readlines()]
else:
    print("UYARI: Model veya labels dosyası bulunamadı!")

def tahmin_et(img_path):
    img = Image.open(img_path).convert("RGB").resize((224, 224))
    img = np.array(img, dtype=np.float32) / 255.0
    img = np.expand_dims(img, axis=0)

    interpreter.set_tensor(input_details[0]['index'], img)
    interpreter.invoke()
    output = interpreter.get_tensor(output_details[0]['index'])[0]
    index = int(np.argmax(output))
    yuzde = round(float(output[index]) * 100, 2)
    
    # Label dosyasındaki sıralamaya göre ismi döndürür
    label_text = labels[index] if index < len(labels) else "Bilinmiyor"
    return label_text, yuzde

# --- ROUTER (SAYFA YÖNETİMİ) ---
@app.route("/")
def home():
    return redirect(url_for("index")) if "username" in session else redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    hata = None
    if request.method == "POST":
        username, password = request.form["username"], request.form["password"]
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
        user = c.fetchone()
        conn.close()
        if user:
            session["username"] = username
            return redirect(url_for("index"))
        hata = "Kullanıcı adı veya şifre yanlış!"
    return render_template("login.html", hata=hata)

@app.route("/register", methods=["GET", "POST"])
def register():
    hata = None
    if request.method == "POST":
        username, password = request.form["username"], request.form["password"]
        email = request.form.get("recovery_email")
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("INSERT INTO users (username, password, recovery_email) VALUES (?, ?, ?)", (username, password, email))
            conn.commit()
            conn.close()
            return redirect(url_for("login", msg="Başarılı!"))
        except:
            hata = "Bu kullanıcı adı zaten mevcut."
    return render_template("register.html", hata=hata)

@app.route("/index")
def index():
    if "username" not in session: return redirect(url_for("login"))
    return render_template("index.html", username=session["username"])

@app.route("/tahmin", methods=["POST"])
def tahmin():
    if "username" not in session: return redirect(url_for("login"))
    dosya = request.files["foto"]
    if dosya:
        dosya_adi = f"{session['username']}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{dosya.filename}"
        yol = os.path.join(UPLOAD_FOLDER, dosya_adi)
        dosya.save(yol)
        sonuc, yuzde = tahmin_et(yol)
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO fotolar (kullanici, dosya_yolu, yuklenme_zamani) VALUES (?, ?, ?)", 
                  (session["username"], dosya_adi, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return render_template("index.html", sonuc=sonuc, yuzde=yuzde, username=session["username"])
    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# Render için port ayarı
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
