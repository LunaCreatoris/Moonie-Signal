# Pinned by tag and digest (multi-platform index): a moved tag never changes what is built
FROM python:3.13.18-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
# Every package, transitive ones included, is pinned in requirements.txt
RUN pip install --no-cache-dir --no-deps -r requirements.txt
COPY app.py .

# 10001 owns the push_token secret file on the host (mode 0400)
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin moonie
USER 10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD ["python", "-c", "import os, urllib.request; port = os.environ.get('MOONIE_HTTP_PORT') or '8080'; urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=4)"]
CMD ["python", "app.py"]
