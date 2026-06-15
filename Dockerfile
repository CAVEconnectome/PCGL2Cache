# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.14
FROM python:${PYTHON_VERSION}-slim

ENV GIT_SSL_NO_VERIFY=1
# nginx + supervisor serve the feature API; build-essential builds the uwsgi wheel.
# /root/.cloudvolume/secrets is the pipeline worker's secret mount (it runs as root).
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential nginx supervisor procps \
  && (id nginx >/dev/null 2>&1 || useradd -r -d /home/nginx -s /bin/bash nginx) \
  && mkdir -p /etc/uwsgi /home/nginx/.cloudvolume/secrets /root/.cloudvolume/secrets \
  && chown -R nginx /home/nginx \
  && rm -rf /var/lib/apt/lists/*

COPY override/nginx.conf /etc/nginx/nginx.conf
COPY override/timeout.conf /etc/nginx/conf.d/timeout.conf
COPY override/supervisord.conf /etc/supervisor/supervisord.conf
COPY uwsgi.ini /etc/uwsgi/uwsgi.ini

# Pin zstandard to a known-good build (mirrors pcg); kvdbclient pulls zstandard for
# compression and wheel resolution can otherwise drift.
RUN pip install --no-cache-dir --no-deps --force-reinstall "zstandard>=0.23.0"

# Deps before source: a source-only change (the common tag build) reuses this layer.
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade -r requirements.txt

COPY . /app
WORKDIR /app

# Default: the feature API. Pipeline workers override the command (cfg.image()).
CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
