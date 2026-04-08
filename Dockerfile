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

# Criar usuário não-root para segurança (issue #11)
RUN adduser --disabled-password --gecos "" appuser

# Criar diretórios necessários e ajustar permissões
RUN mkdir -p /app/logs /app/frontend/assets/uploads \
    && chown -R appuser:appuser /app

# Copiar código-fonte
COPY --chown=appuser:appuser src /app/src
COPY --chown=appuser:appuser frontend /app/frontend

# Executar como usuário não-root
USER appuser

# Comando para rodar a aplicação
EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--loop", "uvloop"]
