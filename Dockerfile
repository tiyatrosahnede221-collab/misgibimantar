# 1. Daha stabil ve hafif bir taban kullanıyoruz
FROM python:3.9-slim

# 2. Sistem paketlerini güncelliyoruz
# libgl1-mesa-glx yerine modern libgl1 paketini kullanıyoruz
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 3. Çalışma dizinini ayarla
WORKDIR /app

# 4. Pip'i güncelle ve bağımlılıkları yükle
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 5. Tüm proje dosyalarını kopyala
COPY . .

# 6. Render için port ayarı
EXPOSE 10000

# 7. Gunicorn ayarları: Bellek dostu ve stabil yapılandırma
# Workers 1 (RAM koruması), Threads 4 (Eşzamanlılık)
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--workers", "1", "--threads", "4", "--timeout", "120", "app:app"]
