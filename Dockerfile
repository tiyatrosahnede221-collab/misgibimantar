# 1. Daha stabil ve hafif bir taban kullanıyoruz
FROM python:3.9-slim

# 2. TensorFlow ve OpenCV gibi kütüphanelerin ihtiyaç duyduğu sistem paketlerini ekliyoruz
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 3. Çalışma dizinini ayarla
WORKDIR /app

# 4. Pip'i güncelle ve bağımlılıkları yükle (Hata payını azaltır)
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# 5. Tüm proje dosyalarını kopyala
COPY . .

# 6. Render için portu 10000 olarak ayarla (Render'ın standart portu budur)
EXPOSE 10000

# 7. Kritik Değişiklik: Worker sayısını 1'e düşürüp thread ekledik.
# Bu sayede RAM kullanımı azalır ama uygulama aynı anda birden fazla işi yapabilir.
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--workers", "1", "--threads", "4", "--timeout", "120", "app:app"]
