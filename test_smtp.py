import os
import sqlite3
import secrets
import smtplib
import socket
from email.message import EmailMessage
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory
import tensorflow as tf
import numpy as np
from PIL import Image

# --- 1. SİSTEM VE DOSYA YOLU AYARLARI ---
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
os.environ['TENSORFLOW_INTEROP_PARALLELISM_THREADS'] = '1'
os.environ['TENSORFLOW_INTRAOP_PARALLELISM_THREADS'] = '1'

# Render/Linux uyumluluğu için tam yollar
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "konumlar.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "fotolar")
MODEL_PATH = os.path.join(BASE_DIR, "model_unquant.tflite")
LABEL_PATH = os.path.join(BASE_DIR, "labels.txt")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "gizli_anahtar_98765")

# --- 2. SMTP AYARLARI (GMAIL) ---
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = "erkanerakman137@gmail.com"
SMTP_PASS = "nrqv nmar ciif sjgs" # Uygulama Şifren
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)

# --- 3. VERİTABANI VE KLASÖR HAZIRLIĞI ---
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        username TEXT UNIQUE, 
        password TEXT, 
        recovery_email TEXT)""")
    c.execute("CREATE TABLE IF NOT EXISTS konumlar (id INTEGER PRIMARY KEY AUTOINCREMENT, kullanici TEXT, konum TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS fotolar (id INTEGER PRIMARY KEY AUTOINCREMENT, kullanici TEXT, dosya_yolu TEXT, yuklenme_zamani TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS password_resets (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, token TEXT UNIQUE, code TEXT, expires_at TEXT)")
    conn.commit()
    conn.close()

init_db()

# --- 4. YAPAY ZEKA MODELİ YÜKLEME ---
labels = []
interpreter = None
input_details = None
output_details = None

try:
    if os.path.exists(MODEL_PATH) and os.path.exists(LABEL_PATH):
        interpreter = tf.lite.Interpreter(model_path=MODEL_PATH)
        interpreter.allocate_tensors()
        input_details = interpreter.get_input_details()
        output_details = interpreter.get_output_details()
        with open(LABEL_PATH, "r", encoding="utf-8") as f:
            labels = [line.strip() for line in f.readlines()]
        print("Model ve Etiketler başarıyla yüklendi.")
    else:
        print("KRİTİK UYARI: Model veya Label dosyası dizinde bulunamadı!")
except Exception as e:
    print(f"Model yükleme hatası: {e}")

# --- 5. YARDIMCI FONKSİYONLAR ---
def tahmin_et(img_path):
    if interpreter is None:
        return "Model Hatası", 0
    img = Image.open(img_path).convert("RGB").resize((224, 224))
    img = np.array(img, dtype=np.float32) / 255.0
    img = np.expand_dims(img, axis=0)
    interpreter.set_tensor(input_details[0]['index'], img)
    interpreter.invoke()
    output = interpreter.get_tensor(output_details[0]['index'])[0]
    index = int(np.argmax(output))
    return labels[index], round(float(output[index]) * 100, 2)

def send_email(to_address, subject, body):
    msg = EmailMessage()
    msg["From"] = SMTP_FROM
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"E-posta hatası: {e}")
        return False

# --- 6. SAYFA YÖNLENDİRMELERİ (ROUTES) ---

@app.route("/")
def home():
    if "username" in session:
        return redirect(url_for("index"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    hata = None
    if request.method == "POST
