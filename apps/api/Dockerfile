FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin roadrisk

COPY pyproject.toml README.md ./
COPY src ./src
COPY apps ./apps

RUN pip install --no-cache-dir ".[api,ml]" \
    && rm -rf /root/.cache/pip

COPY apps/api/docker-entrypoint.sh /usr/local/bin/roadrisk-entrypoint
RUN chmod 755 /usr/local/bin/roadrisk-entrypoint

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=5 \
    CMD python -c "import json,urllib.request; body=json.load(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)); raise SystemExit(0 if body.get('ready') is True else 1)"

ENTRYPOINT ["/usr/local/bin/roadrisk-entrypoint"]
CMD ["python", "-m", "uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
