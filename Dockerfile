FROM python:3.11-slim

WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependências do Python
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Criar diretórios necessários e usuário não-root
RUN mkdir -p /app/logs /app/frontend/assets/uploads \
    && adduser --disabled-password --gecos "" appuser \
    && chown -R appuser /app

# Copiar código-fonte
COPY --chown=appuser src /app/src
COPY --chown=appuser frontend /app/frontend

# Executar como usuário não-root (segurança)
USER appuser

EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--loop", "uvloop"]
