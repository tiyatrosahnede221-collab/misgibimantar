import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
import tensorflow as tf
import numpy as np
from PIL import Image

app = Flask(__name__)
app.secret_key = "izmir_mantar_2026"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "veritabani.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "fotolar")
MODEL_PATH = os.path.join(BASE_DIR, "model_unquant.tflite")
LABEL_PATH = os.path.join(BASE_DIR, "labels.txt")

if not os.path.exists(UPLOAD_FOLDER): os.makedirs(UPLOAD_FOLDER)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, u TEXT UNIQUE, p TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS fotolar (id INTEGER PRIMARY KEY, user TEXT, path TEXT, res TEXT, prob REAL, date TEXT)")
    conn.commit()
    conn.close()

init_db()

interpreter = None
labels = []

def get_model():
    global interpreter, labels
    if interpreter is None:
        interpreter = tf.lite.Interpreter(model_path=MODEL_PATH)
        interpreter.allocate_tensors()
        with open(LABEL_PATH, "r", encoding="utf-8") as f:
            labels = [line.strip() for line in f.readlines()]
    return interpreter, labels

@app.route("/")
def home():
    return redirect(url_for("index")) if "user" in session else redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u, p = request.form.get("u"), request.form.get("p")
        conn = sqlite3.connect(DB_PATH)
        user = conn.execute("SELECT * FROM users WHERE u=? AND p=?", (u, p)).fetchone()
        conn.close()
        if user:
            session["user"] = u
            return redirect(url_for("index"))
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        u, p = request.form.get("u"), request.form.get("p")
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("INSERT INTO users (u, p) VALUES (?, ?)", (u, p))
            conn.commit(); conn.close()
            return redirect(url_for("login"))
        except: return "Kullanıcı adı alınmış."
    return render_template("register.html")

@app.route("/index")
def index():
    if "user" not in session: return redirect(url_for("login"))
    return render_template("index.html", user=session["user"])

@app.route("/tahmin", methods=["POST"])
def tahmin():
    if "user" not in session: return redirect(url_for("login"))
    f = request.files.get("foto")
    if f:
        fname = f"{session['user']}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
        path = os.path.join(UPLOAD_FOLDER, fname)
        f.save(path)
        interp, lbls = get_model()
        img = Image.open(path).convert("RGB").resize((224, 224))
        input_data = np.expand_dims(np.array(img, dtype=np.float32) / 255.0, axis=0)
        interp.set_tensor(interp.get_input_details()[0]['index'], input_data)
        interp.invoke()
        preds = interp.get_tensor(interp.get_output_details()[0]['index'])[0]
        idx = np.argmax(preds)
        res, prob = lbls[idx], round(float(preds[idx]) * 100, 2)
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO fotolar (user, path, res, prob, date) VALUES (?,?,?,?,?)",
                     (session["user"], fname, res, prob, datetime.now().strftime("%d/%m/%Y %H:%M")))
        conn.commit(); conn.close()
        return render_template("index.html", sonuc=res, yuzde=prob, user=session["user"])
    return redirect(url_for("index"))

@app.route("/fotolarim")
def fotolarim():
    if "user" not in session: return redirect(url_for("login"))
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT path, res, prob, date FROM fotolar WHERE user=? ORDER BY id DESC", (session["user"],)).fetchall()
    conn.close()
    return render_template("fotolarim.html", fotolar=rows, user=session["user"])

@app.route("/dosya/<path:filename>")
def dosya(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("login"))

if __name__ == "__main__":
    app.run()
