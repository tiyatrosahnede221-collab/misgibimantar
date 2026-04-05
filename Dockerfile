# 1. Python imajını kullan
FROM python:3.10-slim

# 2. Çalışma dizinini oluştur
WORKDIR /app

# 3. Gerekli kütüphaneleri kopyala ve yükle
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Tüm proje dosyalarını içeri aktar
COPY . .

# 5. Render'ın port ayarını tanımla
ENV PORT=5000

# 6. UYGULAMAYI BAŞLAT (En kritik satır burası, Status 128'i bu çözer)
CMD ["python", "app.py"]
