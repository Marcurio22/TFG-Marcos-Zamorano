FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        gosu \
        libgomp1 \
        libjpeg62-turbo \
        libpng16-16 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd \
    --create-home \
    --home-dir /home/appuser \
    --shell /usr/sbin/nologin \
    --uid 10001 \
    appuser

WORKDIR /app

COPY webapp/requirements.txt /app/webapp/requirements.txt

RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install \
        torch==2.7.1 \
        torchvision==0.22.1 \
        --index-url https://download.pytorch.org/whl/cu118 \
    && grep -vE '^(torch|torchvision|torchaudio)==' \
        /app/webapp/requirements.txt > /tmp/requirements-no-torch.txt \
    && python -m pip install -r /tmp/requirements-no-torch.txt

COPY webapp /app/webapp
COPY docker /app/docker

RUN chmod +x /app/docker/entrypoint.sh \
    && mkdir -p /app/instance \
    && chown -R appuser:appuser /app

WORKDIR /app/webapp

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "--config", "/app/docker/gunicorn.conf.py", "run:app"]
