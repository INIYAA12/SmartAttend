# NOTE: written for deployment but not built/run in the development sandbox.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-optional.txt ./
RUN pip install --no-cache-dir -r requirements.txt && (pip install --no-cache-dir -r requirements-optional.txt || true)

COPY . .
ENV APP_ENV=production HOST=0.0.0.0 PORT=5000
EXPOSE 5000

# One process, many threads: the camera session and job queue live in-process.
CMD ["python", "serve.py"]
