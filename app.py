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

# --- SİSTEM AYARLARI ---
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
os.environ['TENSORFLOW_INTEROP_PARALLELISM_THREADS'] = '1'
os.environ['TENSORFLOW_INTRAOP_PARALLELISM_THREADS'] = '1'

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "mantar_projesi_2026_x")

# Dinamik Yollar
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "konumlar.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "fotolar")
MODEL_PATH = os.path.join(BASE_DIR, "model_unquant.tflite")
LABEL_PATH = os.path.join(BASE_DIR, "labels.txt")

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- VERİTABANI ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, recovery_email TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS fotolar (id INTEGER PRIMARY KEY AUTOINCREMENT, kullanici TEXT, dosya_yolu TEXT, sonuc TEXT, yuzde REAL, zaman TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS password_resets (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, token TEXT UNIQUE, code TEXT, expires_at TEXT)")
    conn.commit()
    conn.close()

init_db()

# --- YAPAY ZEKA ---
labels = []
interpreter = None

def get_model():
    global interpreter, labels
    if interpreter is None:
        if os.path.exists(MODEL_PATH):
            interpreter = tf.lite.Interpreter(model_path=MODEL_PATH)
            interpreter.allocate_tensors()
            with open(LABEL_PATH, "r", encoding="utf-8") as f:
                labels = [line.strip() for line in f.readlines()]
    return interpreter

def tahmin_et(img_path):
    model = get_model()
    if model is None: return "Model Bulunamadı", 0
    
    img = Image.open(img_path).convert("RGB").resize((224, 224))
    img_array = np.array(img, dtype=np.float32) / 255.0
    img_array = np.expand_dims(img_array, axis=0)

    input_details = model.get_input_details()
    output_details = model.get_output_details()
    model.set_tensor(input_details[0]['index'], img_array)
    model.invoke()
    
    predictions = model.get_tensor(output_details[0]['index'])[0]
    idx = np.argmax(predictions)
    return labels[idx], round(float(predictions[idx]) * 100, 2)

# --- SAYFALAR (ROUTES) ---
@app.route("/")
def home():
    return redirect(url_for("index")) if "username" in session else redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    hata = None
    if request.method == "POST":
        u, p = request.form["username"], request.form["password"]
        conn = sqlite3.connect(DB_PATH)
        user = conn.execute("SELECT * FROM users WHERE username=? AND password=?", (u, p)).fetchone()
        conn.close()
        if user:
            session["username"] = u
            return redirect(url_for("index"))
        hata = "Hatalı kullanıcı adı veya şifre!"
    return render_template("login.html", hata=hata, msg=request.args.get("msg"))

@app.route("/register", methods=["GET", "POST"])
def register():
    hata = None
    if request.method == "POST":
        u, p, e = request.form["username"], request.form["password"], request.form.get("recovery_email")
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("INSERT INTO users (username, password, recovery_email) VALUES (?, ?, ?)", (u, p, e))
            conn.commit()
            conn.close()
            return redirect(url_for("login", msg="Kayıt başarılı!"))
        except: hata = "Bu kullanıcı adı zaten alınmış."
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
        fname = f"{session['username']}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
        path = os.path.join(UPLOAD_FOLDER, fname)
        file.save(path)
        res, prob = tahmin_et(path)
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO fotolar (kullanici, dosya_yolu, sonuc, yuzde, zaman) VALUES (?, ?, ?, ?, ?)", 
                     (session["username"], fname, res, prob, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return render_template("index.html", sonuc=res, yuzde=prob, username=session["username"])
    return redirect(url_for("index"))

@app.route("/fotolarim")
def fotolarim():
    if "username" not in session: return redirect(url_for("login"))
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT dosya_yolu, sonuc, yuzde, zaman FROM fotolar WHERE kullanici=? ORDER BY id DESC", (session["username"],)).fetchall()
    conn.close()
    return render_template("fotolarim.html", fotolar=rows, username=session["username"])

@app.route("/fotolar/<path:filename>")
def serve_foto(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
