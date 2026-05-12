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

app = Flask(_name_)
app.secret_key = os.environ.get("SECRET_KEY", "gizli_anahtar")
UPLOAD_FOLDER = "fotolar"

MODEL_PATH = os.path.join("converted_tflite", "model_unquant.tflite")
LABEL_PATH = os.path.join("converted_tflite", "labels.txt")

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def test_smtp_dns():
    try:
        socket.gethostbyname(SMTP_HOST)
        print(f"SMTP_HOST ({SMTP_HOST}) DNS çözümlemesi başarılı.")
    except socket.gaierror as e:
        print(f"SMTP_HOST ({SMTP_HOST}) DNS çözümleme hatası: {e}")
        raise RuntimeError("SMTP_HOST DNS çözümleme başarısız.")

test_smtp_dns()
if not SMTP_USER or not SMTP_PASS:
    raise RuntimeError("SMTP ayarları eksik. Render environment variables ayarlayın.")

def init_db():
    conn = sqlite3.connect("konumlar.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            recovery_email TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS konumlar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kullanici TEXT,
            konum TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS fotolar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kullanici TEXT,
            dosya_yolu TEXT,
            yuklenme_zamani TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            token TEXT UNIQUE,
            code TEXT,
            expires_at TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

if not os.path.exists(MODEL_PATH):
    raise FileNotFoundError(f"Model dosyası bulunamadı: {MODEL_PATH}")
if not os.path.exists(LABEL_PATH):
    raise FileNotFoundError(f"Label dosyası bulunamadı: {LABEL_PATH}")

interpreter = tf.lite.Interpreter(model_path=MODEL_PATH)
interpreter.allocate_tensors()
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

with open(LABEL_PATH, "r", encoding="utf-8") as f:
    labels = [line.strip() for line in f.readlines()]

def tahmin_et(img_path):
    img = Image.open(img_path).resize((224, 224))
    img = np.array(img, dtype=np.float32) / 255.0
    if img.ndim == 2:
        img = np.stack([img, img, img], axis=-1)
    if img.shape[-1] == 4:
        img = img[..., :3]
    img = np.expand_dims(img, axis=0)

    interpreter.set_tensor(input_details[0]['index'], img)
    interpreter.invoke()
    output = interpreter.get_tensor(output_details[0]['index'])[0]
    index = int(np.argmax(output))
    yuzde = round(float(output[index]) * 100, 2)
    return labels[index], yuzde

@app.route("/", methods=["GET"])
def home():
    if "username" in session:
        return redirect(url_for("index"))
    return redirect(url_for("login"))

# ... diğer route fonksiyonları aynı şekilde devam ediyor ...

if _name_ == "_main_":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
