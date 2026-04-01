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

# --- 1. SİSTEM VE RAM AYARLARI ---
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
os.environ['TENSORFLOW_INTEROP_PARALLELISM_THREADS'] = '1'
os.environ['TENSORFLOW_INTRAOP_PARALLELISM_THREADS'] = '1'

app = Flask(__name__)
app.secret_key = "gizli_anahtar"
UPLOAD_FOLDER = "fotolar"

# --- 2. DEĞİŞKEN TANIMLAMALARI (SMTP VE YOLLAR) ---
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = "erkanerakman137@gmail.com"
SMTP_PASS = "nrqv nmar ciif sjgs"
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)

# Render için dinamik dosya yolları
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "model_unquant.tflite")
LABEL_PATH = os.path.join(BASE_DIR, "labels.txt")

# --- 3. KONTROL FONKSİYONLARI ---
def test_smtp_dns():
    try:
        socket.gethostbyname(SMTP_HOST)
        print(f"SMTP_HOST ({SMTP_HOST}) DNS çözümlemesi başarılı.")
        return True
    except socket.gaierror as e:
        print(f"SMTP_HOST ({SMTP_HOST}) DNS çözümleme hatası: {e}")
        return False

# Klasör ve Dosya Kontrolleri
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

if not os.path.exists(MODEL_PATH):
    print(f"HATA: Model dosyası bulunamadı! Aranan yol: {MODEL_PATH}")
if not os.path.exists(LABEL_PATH):
    print(f"HATA: Label dosyası bulunamadı! Aranan yol: {LABEL_PATH}")

# --- 4. VERİTABANI BAŞLATMA ---
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
    c.execute("CREATE TABLE IF NOT EXISTS konumlar (id INTEGER PRIMARY KEY AUTOINCREMENT, kullanici TEXT, konum TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS fotolar (id INTEGER PRIMARY KEY AUTOINCREMENT, kullanici TEXT, dosya_yolu TEXT, yuklenme_zamani TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS password_resets (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, token TEXT UNIQUE, code TEXT, expires_at TEXT)")
    conn.commit()
    conn.close()

init_db()
test_smtp_dns()

# --- 5. MODEL YÜKLEME ---
try:
    interpreter = tf.lite.Interpreter(model_path=MODEL_PATH)
    interpreter.allocate_tensors()
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()
    with open(LABEL_PATH, "r", encoding="utf-8") as f:
        labels = [line.strip() for line in f.readlines()]
    print("Model ve etiketler başarıyla yüklendi.")
except Exception as e:
    print(f"Model yüklenirken kritik hata: {e}")


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

# --- Utility functions for reset ---
def create_reset_entry(username, hours_valid=1):
    token = secrets.token_urlsafe(24)
    code = f"{secrets.randbelow(10**6):06d}"  # 6-digit code
    expires_at = (datetime.utcnow() + timedelta(hours=hours_valid)).isoformat()
    conn = sqlite3.connect("konumlar.db")
    c = conn.cursor()
    c.execute("INSERT INTO password_resets (username, token, code, expires_at) VALUES (?, ?, ?, ?)",
              (username, token, code, expires_at))
    conn.commit()
    conn.close()
    return token, code, expires_at

def validate_token(token):
    conn = sqlite3.connect("konumlar.db")
    c = conn.cursor()
    c.execute("SELECT username, expires_at FROM password_resets WHERE token=?", (token,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    username, expires_at = row
    try:
        if datetime.fromisoformat(expires_at) < datetime.utcnow():
            return None
    except Exception:
        return None
    return username

def validate_code(username, code):
    conn = sqlite3.connect("konumlar.db")
    c = conn.cursor()
    c.execute("SELECT token, expires_at FROM password_resets WHERE username=? AND code=? ORDER BY id DESC LIMIT 1", (username, code))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    token, expires_at = row
    try:
        if datetime.fromisoformat(expires_at) < datetime.utcnow():
            return None
    except Exception:
        return None
    return token

def delete_token(token):
    conn = sqlite3.connect("konumlar.db")
    c = conn.cursor()
    c.execute("DELETE FROM password_resets WHERE token=?", (token,))
    conn.commit()
    conn.close()

def send_email(to_address, subject, body):
    if not SMTP_USER or not SMTP_PASS:
        raise RuntimeError("SMTP_USER veya SMTP_PASS eksik. Lütfen çevre değişkenlerini kontrol edin.")
    try:
        msg = EmailMessage()
        msg["From"] = SMTP_FROM
        msg["To"] = to_address
        msg["Subject"] = subject
        msg.set_content(body)
        print(f"SMTP sunucusuna bağlanılıyor: {SMTP_HOST}:{SMTP_PORT}")
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.set_debuglevel(1)  # Hata ayıklama için SMTP işlemlerini göster
            server.starttls()
            print("SMTP kimlik doğrulama yapılıyor...")
            server.login(SMTP_USER, SMTP_PASS)
            print("Kimlik doğrulama başarılı. E-posta gönderiliyor...")
            server.send_message(msg)
            print("E-posta başarıyla gönderildi.")
    except smtplib.SMTPAuthenticationError as e:
        print(f"SMTP kimlik doğrulama hatası: {e}. Kullanıcı adı: {SMTP_USER}")
        raise RuntimeError("SMTP kimlik doğrulama başarısız. Lütfen kullanıcı adı ve şifrenizi kontrol edin.")
    except smtplib.SMTPConnectError as e:
        print(f"SMTP bağlantı hatası: {e}")
        raise RuntimeError("SMTP sunucusuna bağlanılamadı. Lütfen ağ bağlantınızı kontrol edin.")
    except smtplib.SMTPException as e:
        print(f"SMTP hatası: {e}")
        raise RuntimeError("E-posta gönderimi sırasında bir hata oluştu. Lütfen SMTP yapılandırmanızı kontrol edin.")

# --- Routes ---
@app.route("/", methods=["GET"])
def home():
    if "username" in session:
        return redirect(url_for("index"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    hata = None
    msg = request.args.get("msg")
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        conn = sqlite3.connect("konumlar.db")
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
        user = c.fetchone()
        conn.close()
        if user:
            session["username"] = username
            return redirect(url_for("index"))
        else:
            hata = "Kullanıcı adı veya şifre yanlış!"
    return render_template("login.html", hata=hata, msg=msg)

@app.route("/register", methods=["GET", "POST"])
def register():
    hata = None
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        recovery_email = request.form.get("recovery_email")
        try:
            conn = sqlite3.connect("konumlar.db")
            c = conn.cursor()
            c.execute("INSERT INTO users (username, password, recovery_email) VALUES (?, ?, ?)",
                      (username, password, recovery_email))
            conn.commit()
            conn.close()
            return redirect(url_for("login", msg="Kayıt başarılı. Giriş yapabilirsiniz."))
        except sqlite3.IntegrityError:
            hata = "Bu kullanıcı adı zaten alınmış!"
    return render_template("register.html", hata=hata)

@app.route("/logout")
def logout():
    session.pop("username", None)
    return redirect(url_for("login"))

@app.route("/index", methods=["GET"])
def index():
    if "username" not in session:
        return redirect(url_for("login"))
    return render_template("index.html", username=session["username"])

@app.route("/tahmin", methods=["POST"])
def tahmin():
    if "username" not in session:
        return redirect(url_for("login"))
    dosya = request.files["foto"]
    dosya_adi = f"{session['username']}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{dosya.filename}"
    yol = os.path.join(UPLOAD_FOLDER, dosya_adi)
    dosya.save(yol)
    sonuc, yuzde = tahmin_et(yol)
    conn = sqlite3.connect("konumlar.db")
    c = conn.cursor()
    c.execute("INSERT INTO fotolar (kullanici, dosya_yolu, yuklenme_zamani) VALUES (?, ?, ?)",
              (session["username"], dosya_adi, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return render_template("index.html", sonuc=sonuc, yuzde=yuzde, username=session["username"])

@app.route("/fotolarim")
def fotolarim():
    if "username" not in session:
        return redirect(url_for("login"))
    conn = sqlite3.connect("konumlar.db")
    c = conn.cursor()
    c.execute("SELECT dosya_yolu, yuklenme_zamani FROM fotolar WHERE kullanici=? ORDER BY id DESC", (session["username"],))
    fotolar = c.fetchall()
    conn.close()
    return render_template("fotolarim.html", fotolar=fotolar, username=session["username"])

@app.route("/fotolar/<path:filename>")
def fotolar_serve(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# --- Forgot / verify / reset flows ---
@app.route("/forgot", methods=["GET", "POST"])
def forgot():
    info = None
    show_code = None
    if request.method == "POST":
        username = request.form.get("username")  # Kullanıcının girişte belirttiği kullanıcı adı
        conn = sqlite3.connect("konumlar.db")
        c = conn.cursor()
        c.execute("SELECT recovery_email FROM users WHERE username=?", (username,))
        row = c.fetchone()
        conn.close()
        if not row:
            info = "Bu kullanıcı adıyla kayıtlı bir e-posta bulunamadı."
        else:
            recovery_email = row[0]
            if not recovery_email:
                info = "Bu kullanıcı için kayıtlı bir kurtarma e-posta adresi yok."
            else:
                token, code, expires_at = create_reset_entry(username)
                try:
                    body = f"Şifre sıfırlama kodunuz: {code}\nBu kod {expires_at} UTC tarihine kadar geçerlidir.\nLink: {url_for('reset_password', token=token, _external=True)}"
                    send_email(recovery_email, "Şifre Sıfırlama Kodu", body)
                    info = "Reset kodu e-postaya gönderildi. Gelen kutunuzu kontrol edin."
                except Exception as e:
                    show_code = code
                    info = f"E-posta gönderilemedi; geliştirici modunda kod sayfada gösteriliyor. Hata: {e}"
    return render_template("forgot_password.html", info=info, reset_link=None, show_code=show_code)

@app.route("/verify_code", methods=["POST"])
def verify_code():
    username = request.form.get("username")
    code = request.form.get("code")
    if not username or not code:
        return render_template("forgot_password.html", info="Eksik bilgi", reset_link=None)
    token = validate_code(username, code)
    if not token:
        return render_template("forgot_password.html", info="Kod geçersiz veya süresi dolmuş.", reset_link=None)
    return redirect(url_for("reset_password", token=token))

@app.route("/reset/<token>", methods=["GET", "POST"])
def reset_password(token):
    username = validate_token(token)
    if not username:
        return render_template("reset_password.html", error="Geçersiz veya süresi dolmuş token.", token=None)
    if request.method == "POST":
        new_password = request.form.get("password")
        conn = sqlite3.connect("konumlar.db")
        c = conn.cursor()
        c.execute("UPDATE users SET password=? WHERE username=?", (new_password, username))
        conn.commit()
        conn.close()
        delete_token(token)
        return redirect(url_for("login", msg="Şifre başarıyla değiştirildi. Giriş yapabilirsiniz."))
    return render_template("reset_password.html", username=username, token=token, error=None)

@app.route("/konumkaydet", methods=["POST"])
def konumkaydet():
    if "username" not in session:
        return jsonify({"status": "error", "msg": "Giriş yapmalısınız!"}), 401
    data = request.get_json()
    kullanici = session["username"]
    konum = data.get("konum")
    if kullanici and konum:
        conn = sqlite3.connect("konumlar.db")
        c = conn.cursor()
        c.execute("INSERT INTO konumlar (kullanici, konum) VALUES (?, ?)", (kullanici, konum))
        conn.commit()
        conn.close()
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"}), 400

@app.route("/konumum", methods=["GET"])
def konumum():
    if "username" not in session:
        return redirect(url_for("login"))
    kullanici = session["username"]
    conn = sqlite3.connect("konumlar.db")
    c = conn.cursor()
    c.execute("SELECT konum FROM konumlar WHERE kullanici=? ORDER BY id DESC", (kullanici,))
    konumlar = [row[0] for row in c.fetchall()]
    conn.close()
    return render_template("konumum.html", konumlar=konumlar, username=kullanici)

# SMTP bağlantısını test etmek için bir endpoint ekliyorum.
@app.route("/test_email", methods=["GET"])
def test_email():
    try:
        test_email_address = SMTP_USER  # Test için kendi e-posta adresinizi kullanın
        subject = "SMTP Test"
        body = "Bu bir test e-postasıdır. SMTP bağlantısı başarılı."
        send_email(test_email_address, subject, body)
        return "Test e-postası başarıyla gönderildi. Gelen kutunuzu kontrol edin."
    except Exception as e:
        return f"E-posta gönderiminde hata oluştu: {e}"

import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
