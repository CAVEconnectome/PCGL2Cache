# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.12
FROM tiangolo/uwsgi-nginx-flask:python${PYTHON_VERSION}

ENV GIT_SSL_NO_VERIFY=1
RUN mkdir -p /home/nginx/.cloudvolume/secrets \
  && chown -R nginx /home/nginx \
  && usermod -d /home/nginx -s /bin/bash nginx

# Pin zstandard to a known-good build (mirrors pcgv3); kvdbclient pulls
# zstandard for compression and wheel resolution can otherwise drift.
RUN pip install --no-cache-dir --no-deps --force-reinstall zstandard>=0.23.0

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade -r requirements.txt

COPY . /app
