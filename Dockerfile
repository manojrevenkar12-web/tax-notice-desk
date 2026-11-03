FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm build

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils tesseract-ocr tesseract-ocr-deu \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml ./
COPY tnd/ tnd/
COPY config/ config/
COPY corpus/ corpus/
COPY prompts/ prompts/
COPY reports/ reports/
RUN pip install --no-cache-dir .
COPY --from=web /web/dist web/dist
ENV TND_ENV=production
USER nobody
EXPOSE 8095
CMD ["uvicorn", "tnd.desk.app:app", "--host", "0.0.0.0", "--port", "8095"]
