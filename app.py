import os, sqlite3, json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, jsonify
from flask_mail import Mail, Message
import tensorflow as tf
import numpy as np
from PIL import Image

app = Flask(__name__)
app.secret_key = "izmir_konak_2026"

# E-Posta Ayarları (Gmail örneği)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'senin_mailin@gmail.com' # BURAYI DOLDUR
app.config['MAIL_PASSWORD'] = 'uygulama_sifren'       # BURAYI DOLDUR
mail = Mail(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "mantar_v2.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static/uploads")
MODEL_PATH = os.path.join(BASE_DIR, "model_unquant.tflite")
LABEL_PATH = os.path.join(BASE_DIR, "labels.txt")

if not os.path.exists(UPLOAD_FOLDER): os.makedirs(UPLOAD_FOLDER)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    # E-posta ve Konum kolonları eklendi
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, u TEXT UNIQUE, p TEXT, email TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS fotolar (id INTEGER PRIMARY KEY, user TEXT, path TEXT, res TEXT, prob REAL, lat TEXT, lon TEXT, date TEXT)")
    conn.commit()
    conn.close()

init_db()

# Model Yükleme
interpreter = tf.lite.Interpreter(model_path=MODEL_PATH)
interpreter.allocate_tensors()
with open(LABEL_PATH, "r", encoding="utf-8") as f:
    labels = [line.strip() for line in f.readlines()]

@app.route("/")
def home():
    return redirect(url_for("index")) if "user" in session else redirect(url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        u, p, e = request.form.get("u"), request.form.get("p"), request.form.get("email")
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("INSERT INTO users (u, p, email) VALUES (?, ?, ?)", (u, p, e))
            conn.commit(); conn.close()
            # Hoşgeldin Maili Gönder (Opsiyonel)
            msg = Message('Mis Gibi Mantar - Üyeliğiniz Onaylandı', sender='noreply@mantar.com', recipients=[e])
            msg.body = f"Merhaba {u}, Mantar Teşhis Sistemine hoş geldin! LGS yolunda başarılar dileriz."
            # mail.send(msg) # Şifrelerin doğruysa bu satırı aktif et
            return redirect(url_for("login"))
        except: return "Hata: Kullanıcı adı veya Email zaten kayıtlı."
    return render_template("register.html")

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

@app.route("/tahmin", methods=["POST"])
def tahmin():
    if "user" not in session: return redirect(url_for("login"))
    f = request.files.get("foto")
    lat = request.form.get("lat")
    lon = request.form.get("lon")
    
    if f:
        fname = f"{session['user']}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
        path = os.path.join(UPLOAD_FOLDER, fname)
        f.save(path)
        
        img = Image.open(path).convert("RGB").resize((224, 224))
        input_data = np.expand_dims(np.array(img, dtype=np.float32) / 255.0, axis=0)
        
        interpreter.set_tensor(interpreter.get_input_details()[0]['index'], input_data)
        interpreter.invoke()
        preds = interpreter.get_tensor(interpreter.get_output_details()[0]['index'])[0]
        
        idx = np.argmax(preds)
        res = labels[idx].split(' ', 1)[-1] if ' ' in labels[idx] else labels[idx]
        prob = round(float(preds[idx]) * 100, 2)
        
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO fotolar (user, path, res, prob, lat, lon, date) VALUES (?,?,?,?,?,?,?)",
                     (session["user"], fname, res, prob, lat, lon, datetime.now().strftime("%d/%m/%Y %H:%M")))
        conn.commit(); conn.close()
        return jsonify({"sonuc": res, "yuzde": prob})
    return "Dosya yüklenemedi", 400

@app.route("/index")
def index():
    if "user" not in session: return redirect(url_for("login"))
    return render_template("index.html", user=session["user"])

@app.route("/fotolarim")
def fotolarim():
    if "user" not in session: return redirect(url_for("login"))
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT path, res, prob, lat, lon, date FROM fotolar WHERE user=? ORDER BY id DESC", (session["user"],)).fetchall()
    conn.close()
    return render_template("fotolarim.html", fotolar=rows)

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(port=10000)
