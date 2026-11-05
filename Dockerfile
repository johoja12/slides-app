FROM python:3.13-slim@sha256:ae14d4ce8771606477a81446e7ef429edd6762305fc50c84507c1041fa8285d1
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends libreoffice-impress poppler-utils fonts-crosextra-carlito fonts-crosextra-caladea fonts-liberation2 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py pptx_preview.py .
COPY templates templates
COPY static static
USER 1024:100
CMD ["gunicorn", "--bind=0.0.0.0:8000", "--workers=2", "--threads=4", "--timeout=30", "app:app"]
