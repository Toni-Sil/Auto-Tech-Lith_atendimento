# ╔════════════════════════════════════════════════════════════════╗
# ║  STAGE 1 — Frontend build (Node + Tailwind)                  ║
# ╚════════════════════════════════════════════════════════════════╝
FROM node:20-alpine AS frontend-build

WORKDIR /frontend

# Instala deps Node
COPY frontend/package*.json ./
RUN npm ci || npm install

# Copia fontes CSS e HTMLs/JS (necessarios para o purge do Tailwind)
COPY frontend/ ./

# Compila Tailwind — gera css/tailwind.min.css
RUN npm run build:css


# ╔════════════════════════════════════════════════════════════════╗
# ║  STAGE 2 — Python runtime                                    ║
# ╚════════════════════════════════════════════════════════════════╝
FROM python:3.11-slim AS runtime

WORKDIR /app

# Deps do sistema (curl para healthcheck, gcc+libpq-dev para psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Deps Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Diretórios de runtime
RUN mkdir -p /app/logs /app/frontend/assets/uploads

# Copia backend
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations

# Copia frontend (HTML/JS/CSS base)
COPY frontend ./frontend

# SUBSTITUI o css compilado pelo output do stage 1 (sem node_modules)
COPY --from=frontend-build /frontend/css/tailwind.min.css ./frontend/css/tailwind.min.css

EXPOSE 8000

CMD ["uvicorn", "src.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--loop", "uvloop"]
