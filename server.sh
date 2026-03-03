#!/bin/bash
# ─────────────────────────────────────────
# server.sh – Gerenciador do servidor FastAPI
# Uso: ./server.sh [start|stop|restart|status|logs]
# ─────────────────────────────────────────

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python3"
UVICORN="$PROJECT_DIR/venv/bin/uvicorn"
LOG_FILE="$PROJECT_DIR/uvicorn.log"
PID_FILE="$PROJECT_DIR/uvicorn.pid"
PORT=8000

start() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "⚠️  Servidor já está rodando (PID: $(cat "$PID_FILE"))"
        return
    fi

    echo "🚀 Iniciando servidor na porta $PORT..."
    cd "$PROJECT_DIR"
    PYTHONPATH="$PROJECT_DIR" "$UVICORN" src.main:app \
        --host 0.0.0.0 \
        --port "$PORT" \
        --reload \
        > "$LOG_FILE" 2>&1 &

    echo $! > "$PID_FILE"
    sleep 2

    if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "✅ Servidor iniciado! PID: $(cat "$PID_FILE")"
        echo "   URL: http://localhost:$PORT"
        echo "   Logs: $LOG_FILE"
    else
        echo "❌ Falha ao iniciar servidor. Verifique o log: $LOG_FILE"
        tail -n 20 "$LOG_FILE"
    fi
}

stop() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "🛑 Parando servidor (PID: $(cat "$PID_FILE"))..."
        kill "$(cat "$PID_FILE")" 2>/dev/null
        pkill -f "uvicorn src.main:app" 2>/dev/null
        rm -f "$PID_FILE"
        echo "✅ Servidor parado."
    else
        echo "⚠️  Servidor não estava rodando."
        # Kill anyway to be safe
        pkill -f "uvicorn src.main:app" 2>/dev/null
        fuser -k "${PORT}/tcp" 2>/dev/null
        rm -f "$PID_FILE"
    fi
}

status() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "✅ Servidor está RODANDO | PID: $(cat "$PID_FILE") | http://localhost:$PORT"
    else
        echo "❌ Servidor está PARADO"
    fi
}

logs() {
    if [ -f "$LOG_FILE" ]; then
        tail -n 50 "$LOG_FILE"
    else
        echo "Nenhum arquivo de log encontrado: $LOG_FILE"
    fi
}

case "${1:-start}" in
    start)   start ;;
    stop)    stop ;;
    restart) stop; sleep 1; start ;;
    status)  status ;;
    logs)    logs ;;
    *)
        echo "Uso: $0 {start|stop|restart|status|logs}"
        exit 1
        ;;
esac
