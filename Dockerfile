# SkyMatrix — single-process fare board. Do NOT run more than one replica of this
# image: search progress lives in an in-memory registry (backend/app.py `_streams`)
# and the Kiwi rate limiter is process-global.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# SQLite cache, airport table and the merged CA file all land in /app/data — mount a
# volume there so the cache survives a container restart (the app works without it,
# the first visitor after a restart just re-fetches).
VOLUME ["/app/data"]

EXPOSE 8712

# run.py is the documented entrypoint; --no-open skips the browser launch.
CMD ["python", "run.py", "--host", "0.0.0.0", "--port", "8712", "--no-open"]
