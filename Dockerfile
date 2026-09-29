FROM python:3.12-slim

# LibreOffice (headless Writer) renders the filled DOCX to PDF. Liberation fonts are
# metric-compatible with Times New Roman / Arial used by the form, so the layout holds.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libreoffice-writer-nogui fonts-liberation fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    HOME=/tmp

WORKDIR /app
COPY pyproject.toml ./
COPY formfill ./formfill
RUN pip install --no-cache-dir ".[dev]"
COPY tests ./tests
COPY forms ./forms

RUN useradd --create-home --uid 1000 app && mkdir -p /data && chown app /data
USER app
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

CMD ["uvicorn", "formfill.api:app", "--host", "0.0.0.0", "--port", "8000"]
