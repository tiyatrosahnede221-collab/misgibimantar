import os
import smtplib
from email.message import EmailMessage

SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)
TO = os.environ.get("TEST_TO", SMTP_USER)  # test alıcı, default olarak SMTP_USER

msg = EmailMessage()
msg["From"] = SMTP_FROM
msg["To"] = TO
msg["Subject"] = "Test E-postası"
msg.set_content("Bu bir test e-postasıdır.")

print("SMTP_HOST:", SMTP_HOST, "SMTP_PORT:", SMTP_PORT, "SMTP_USER:", SMTP_USER)

try:
    if SMTP_PORT == 465:
        server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10)
        server.login(SMTP_USER, SMTP_PASS)
    else:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
    server.send_message(msg)
    server.quit()
    print("E-posta gönderildi.")
except Exception as e:
    print("E-posta gönderilemedi. Hata:", e)