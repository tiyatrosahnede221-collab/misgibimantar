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

# TFLite Runtime: TensorFlow'un devasa yükünden kurtulmak için
try:
    from tflite_runtime.interpreter import Interpreter
except ImportError:
    import tensorflow as tf
    Interpreter = tf.lite.Interpreter

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "gizli_anahtar_mantar_123")

# --- YOLLAR (Windows yolları silindi, Render/Linux uyumlu hale getirildi) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "fotolar")
# Model ve Labels dosyalarını 'converted_tflite' klasörü içine koyduysan:
MODEL_PATH = os.path.join(BASE_DIR, "converted_tflite", "model_unquant.tflite")
LABEL_PATH = os.path.join(BASE_DIR, "converted_tflite", "labels.txt")
DB_PATH = os.path.join(BASE_DIR, "konumlar.db")

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# SMTP Yapılandırması
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "erkanerakman137@gmail.com"
SMTP_PASS = "nrqv nmar ciif sjgs" 

# --- VERİTABANI FONKSİYONLARI ---
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, recovery_email TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS konumlar (id INTEGER PRIMARY KEY AUTOINCREMENT, kullanici TEXT, konum TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS fotolar (id INTEGER PRIMARY KEY AUTOINCREMENT, kullanici TEXT, dosya_yolu TEXT, yuklenme_zamani TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS password_resets (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, token TEXT UNIQUE, code TEXT, expires_at TEXT)")
    conn.commit()
    conn.close()

init_db()

# --- MODEL YÜKLEME ---
if os.path.exists(MODEL_PATH):
    interpreter = Interpreter(model_path=MODEL_PATH)
    interpreter.allocate_tensors()
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()
    with open(LABEL_PATH, "r", encoding="utf-8") as f:
        labels = [line.strip() for line in f.readlines()]
else:
    print(f"HATA: Model dosyası bulunamadı! Yol: {MODEL_PATH}")

def tahmin_et(img_path):
    img = Image.open(img_path).convert("RGB").resize((224, 224))
    img = np.array(img, dtype=np.float32) / 255.0
    img = np.expand_dims(img, axis=0)
    
    interpreter.set_tensor(input_details[0]['index'], img)
    interpreter.invoke()
    output = interpreter.get_tensor(output_details[0]['index'])[0]
    index = int(np.argmax(output))
    yuzde = round(float(output[index]) * 100, 2)
    return labels[index], yuzde

# --- EMAIL SİSTEMİ ---
def send_email(to_address, subject, body):
    msg = EmailMessage()
    msg["From"] = SMTP_USER
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)

# --- ROUTES ---
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
        hata = "Hatalı giriş!"
    return render_template("login.html", hata=hata)

@app.route("/register", methods=["GET", "POST"])
def register():
    hata = None
    if request.method == "POST":
        username, password = request.form["username"], request.form["password"]
        email = request.form.get("recovery_email")
        try:
            conn = get_db_connection()
            conn.execute("INSERT INTO users (username, password, recovery_email) VALUES (?, ?, ?)", (username, password, email))
            conn.commit()
            conn.close()
            return redirect(url_for("login", msg="Kayıt başarılı!"))
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
    dosya = request.files.get("foto")
    if dosya:
        filename = f"{session['username']}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{dosya.filename}"
        yol = os.path.join(UPLOAD_FOLDER, filename)
        dosya.save(yol)
        sonuc, yuzde = tahmin_et(yol)
        
        conn = get_db_connection()
        conn.execute("INSERT INTO fotolar (kullanici, dosya_yolu, yuklenme_zamani) VALUES (?, ?, ?)", 
                     (session["username"], filename, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return render_template("index.html", sonuc=sonuc, yuzde=yuzde, username=session["username"])
    return redirect(url_for("index"))

@app.route("/fotolar/<path:filename>")
def fotolar_serve(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
