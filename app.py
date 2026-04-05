@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("u") # HTML'deki name="u" ile aynı olmalı
        p = request.form.get("p") # HTML'deki name="p" ile aynı olmalı
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
        u = request.form.get("u")
        p = request.form.get("p")
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("INSERT INTO users (u, p) VALUES (?, ?)", (u, p))
            conn.commit()
            conn.close()
            return redirect(url_for("login"))
        except:
            return "Hata: Bu kullanıcı adı zaten alınmış olabilir."
    return render_template("register.html")
