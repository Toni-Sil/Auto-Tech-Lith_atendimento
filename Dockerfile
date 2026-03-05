FROM python:3.10-slim

WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependências do Python
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Criar diretórios necessários
RUN mkdir -p /app/logs /app/frontend/assets/uploads

# Copiar código-fonte
COPY src /app/src
COPY frontend /app/frontend

# Comando para rodar a aplicação
EXPOSE 8000
CMD ["python", "-m", "src.main"]
