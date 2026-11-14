# Chrome & Oak prototype: one container serving the FastAPI back end and the built React UI on one port.

# 1. Build the UI
FROM node:22-alpine AS ui
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

# 2. Run the API and serve the built UI
FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY api/requirements.txt api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt
COPY api/ api/
COPY data/raw/ data/raw/
COPY data/clean/ data/clean/
COPY output/ output/
COPY --from=ui /ui/dist ui/dist
EXPOSE 8000
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
