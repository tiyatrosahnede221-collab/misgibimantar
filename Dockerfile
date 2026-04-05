FROM python:3.10-slim

# Sistem kütüphanelerini güncelle
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Önce kütüphaneleri kur (Cache avantajı sağlar)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Tüm dosyaları kopyala
COPY . .

# Fotoğraflar için klasör oluştur
RUN mkdir -p fotolar

# Uygulamayı Gunicorn ile başlat (Performans modu)
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--workers", "1", "--threads", "8", "--timeout", "0", "app:app"]
