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

# --- 1. SİSTEM VE DOSYA YOLU AYARLARI ---
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
os.environ['TENSORFLOW_INTEROP_PARALLELISM_THREADS'] = '1'
os.environ['TENSORFLOW_INTRAOP_PARALLELISM_THREADS'] = '1'

# Dinamik yollar (Render uyumluluğu için kritik)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "konumlar.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "fotolar")
MODEL_PATH = os.path.join(BASE_DIR, "model_unquant.tflite")
LABEL_PATH = os.path.join(BASE_DIR, "labels.txt")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "gizli_anahtar_123")

# --- 2. SMTP AYARLARI ---
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = "erkanerakman137@gmail.com"
SMTP_PASS = "nrqv nmar ciif sjgs"
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)

# --- 3. KONTROL VE BAŞLATMA ---
def test_smtp_dns():
    try:
        socket.gethostbyname(SMTP_HOST)
        return True
    except:
        return False

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, recovery_email TEXT)""")
    c.execute("CREATE TABLE IF NOT EXISTS konumlar (id INTEGER PRIMARY KEY AUTOINCREMENT, kullanici TEXT, konum TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS fotolar (id INTEGER PRIMARY KEY AUTOINCREMENT, kullanici TEXT, dosya_yolu TEXT, yuklenme_zamani TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS password_resets (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, token TEXT UNIQUE, code TEXT, expires_at TEXT)")
    conn.commit()
    conn.close()

init_db()

# --- 4. MODEL YÜKLEME ---
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
        print("Model yüklendi.")
    else:
        print("Model veya Label dosyası eksik!")
except Exception as e:
    print(f"Model hatası: {e}")

# --- 5. FONKSİYONLAR ---
def tahmin_et(img_path):
    if interpreter is None: return "Model Yüklenemedi", 0
    img = Image.open(img_path).convert("RGB").resize((224, 224))
    img = np.array(img, dtype=np.float32) / 255.0
    img = np.expand_dims(img, axis=0)
    interpreter.set_tensor(input_details[0]['index'], img)
    interpreter.invoke()
    output = interpreter.get_tensor(output_details[0]['index'])[0]
    index = int(np.argmax(output))
    return labels[index], round(float(output[index]) * 100, 2)

def create_reset_entry(username):
    token = secrets.token_urlsafe(24)
    code = f"{secrets.randbelow(10**6):06d}"
    expires_at = (datetime.utcnow() + timedelta(hours=1)).isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO password_resets (username, token, code, expires_at) VALUES (?, ?, ?, ?)", (username, token, code, expires_at))
    conn.commit()
    conn.close()
    return token, code, expires_at

def send_email(to_address, subject, body):
    msg = EmailMessage()
    msg["From"] = SMTP_FROM
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)

# --- 6. ROUTES ---
@app.route("/")
def home():
    return redirect(url_for("index")) if "username" in session else redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    hata = None
    if request.method == "POST":
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=? AND password=?", (request.form["username"], request.form["password"]))
        user = c.fetchone()
        conn.close()
        if user:
            session["username"] = request.form["username"]
            return redirect(url_for("index"))
        hata = "Hatalı giriş!"
    return render_template("login.html", hata=hata, msg=request.args.get("msg"))

@app.route("/register", methods=["GET", "POST"])
def register():
    hata = None
    if request.method == "POST":
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("INSERT INTO users (username, password, recovery_email) VALUES (?, ?, ?)", 
                     (request.form["username"], request.form["password"], request.form.get("recovery_email")))
            conn.commit()
            conn.close()
            return redirect(url_for("login", msg="Kayıt başarılı."))
        except: hata = "Bu kullanıcı adı zaten var."
    return render_template("register.html", hata=hata)

@app.route("/index")
def index():
    if "username" not in session: return redirect(url_for("login"))
    return render_template("index.html", username=session["username"])

@app.route("/tahmin", methods=["POST"])
def tahmin():
    if "username" not in session: return redirect(url_for("login"))
    dosya = request.files["foto"]
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

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/fotolarim")
def fotolarim():
    if "username" not in session: return redirect(url_for("login"))
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT dosya_yolu, yuklenme_zamani FROM fotolar WHERE kullanici=? ORDER BY id DESC", (session["username"],))
    fotolar = c.fetchall()
    conn.close()
    return render_template("fotolarim.html", fotolar=fotolar, username=session["username"])

@app.route("/fotolar/<path:filename>")
def fotolar_serve(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
