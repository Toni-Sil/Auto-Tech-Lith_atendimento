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

# Criar diretórios necessários
RUN mkdir -p /app/logs /app/frontend/assets/uploads

# Copiar código-fonte
COPY src /app/src
COPY frontend /app/frontend

# SECURITY: executar como usuário não-root
RUN adduser --disabled-password --gecos "" appuser \
    && chown -R appuser /app /app/logs /app/frontend/assets/uploads
USER appuser

# Comando para rodar a aplicação
EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--loop", "uvloop"]
