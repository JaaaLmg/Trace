FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ripgrep \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /app/backend/requirements.txt

COPY backend /app/backend
COPY eval /app/eval

RUN chmod +x /app/backend/docker/entrypoint.sh \
    && mkdir -p /app/.pytest_tmp_experiments

WORKDIR /app/backend
ENTRYPOINT ["/app/backend/docker/entrypoint.sh"]
CMD ["api"]
