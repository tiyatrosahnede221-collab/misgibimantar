FROM python:3.10-slim

# Sistem kütüphanelerini kur
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Kütüphaneleri kur
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Proje dosyalarını kopyala
COPY . .

# Gerekli klasörleri oluştur
RUN mkdir -p static/uploads

# Uygulamayı başlat
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--workers", "1", "--threads", "8", "--timeout", "0", "app:app"]
