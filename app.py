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
import socket

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "gizli_anahtar") # Güvenlik için env'den al
UPLOAD_FOLDER = "fotolar"

# KRİTİK HATA DÜZELTMESİ: Windows dosya yolları Render'da çalışmaz!
# Model dosyalarını proje klasörüne koyup buradan çekmelisiniz.
MODEL_PATH = os.path.join(os.getcwd(), "model_unquant.tflite")
LABEL_PATH = os.path.join(os.getcwd(), "labels.txt")

# SMTP Ayarları
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "erkanerakman137@gmail.com")
SMTP_PASS = os.environ.get("SMTP_PASS", "nrqv nmar ciif sjgs")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)

# Klasör kontrolü
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Veritabanı bağlantısı için yardımcı fonksiyon (Bağlantı hatalarını önler)
def get_db_connection():
    conn = sqlite3.connect("konumlar.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        recovery_email TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS konumlar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kullanici TEXT,
        konum TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS fotolar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kullanici TEXT,
        dosya_yolu TEXT,
        yuklenme_zamani TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS password_resets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        token TEXT UNIQUE,
        code TEXT,
        expires_at TEXT)""")
    conn.commit()
    conn.close()

init_db()

# Model Yükleme (Hata yönetimi eklendi)
interpreter = None
labels = []

if os.path.exists(MODEL_PATH) and os.path.exists(LABEL_PATH):
    try:
        interpreter = tf.lite.Interpreter(model_path=MODEL_PATH)
        interpreter.allocate_tensors()
        with open(LABEL_PATH, "r", encoding="utf-8") as f:
            labels = [line.strip() for line in f.readlines()]
    except Exception as e:
        print(f"Model yükleme hatası: {e}")
else:
    print("UYARI: Model veya Label dosyası bulunamadı! Tahmin özelliği çalışmayacak.")

def tahmin_et(img_path):
    if interpreter is None: return "Model Yüklü Değil", 0
    
    img = Image.open(img_path).convert('RGB').resize((224, 224))
    img = np.array(img, dtype=np.float32) / 255.0
    img = np.expand_dims(img, axis=0)

    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()
    
    interpreter.set_tensor(input_details[0]['index'], img)
    interpreter.invoke()
    output = interpreter.get_tensor(output_details[0]['index'])[0]
    index = int(np.argmax(output))
    yuzde = round(float(output[index]) * 100, 2)
    return labels[index] if labels else "Bilinmiyor", yuzde

# --- Routes (Temel İşlevler Korundu, Bağlantılar Düzenlendi) ---

@app.route("/")
def home():
    return redirect(url_for("index")) if "username" in session else redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    hata = None
    if request.method == "POST":
        username, password = request.form["username"], request.form["password"]
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password)).fetchone()
        conn.close()
        if user:
            session["username"] = username
            return redirect(url_for("index"))
        hata = "Geçersiz kullanıcı adı veya şifre!"
    return render_template("login.html", hata=hata)

@app.route("/register", methods=["GET", "POST"])
def register():
    hata = None
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        email = request.form.get("recovery_email")
        try:
            conn = get_db_connection()
            conn.execute("INSERT INTO users (username, password, recovery_email) VALUES (?, ?, ?)", (username, password, email))
            conn.commit()
            conn.close()
            return redirect(url_for("login", msg="Başarılı!"))
        except:
            hata = "Kullanıcı adı alınmış!"
    return render_template("register.html", hata=hata)

@app.route("/index")
def index():
    if "username" not in session: return redirect(url_for("login"))
    return render_template("index.html", username=session["username"])

@app.route("/tahmin", methods=["POST"])
def tahmin():
    if "username" not in session: return redirect(url_for("login"))
    dosya = request.files.get("foto")
    if dosya:
        dosya_adi = f"{session['username']}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{dosya.filename}"
        yol = os.path.join(UPLOAD_FOLDER, dosya_adi)
        dosya.save(yol)
        sonuc, yuzde = tahmin_et(yol)
        
        conn = get_db_connection()
        conn.execute("INSERT INTO fotolar (kullanici, dosya_yolu, yuklenme_zamani) VALUES (?, ?, ?)",
                     (session["username"], dosya_adi, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return render_template("index.html", sonuc=sonuc, yuzde=yuzde, username=session["username"])
    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# Flask Render Port Ayarı
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
