# DRISHTI single image: API + web UI. Build from the repo root:
#   docker build -f deploy/Dockerfile -t drishti:0.1 .
FROM node:22.12-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12.8-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DRISHTI_HOME=/app DRISHTI_DB=/data/drishti.db
WORKDIR /app
COPY pyproject.toml README.md ./
COPY drishti ./drishti
RUN pip install --no-cache-dir ".[oidc]"
COPY ontology ./ontology
COPY policies ./policies
COPY data ./data
COPY --from=web /web/dist ./web/dist
RUN useradd --system --uid 10001 drishti && mkdir -p /data && chown drishti /data
USER drishti
VOLUME ["/data"]
EXPOSE 8000
# First start builds the demo database from open + synthetic data (~30 s), later starts reuse it.
CMD ["drishti", "demo", "--host", "0.0.0.0", "--port", "8000"]
