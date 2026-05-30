#!/bin/bash
# stop_memory.sh
# Detiene el servidor de memoria en segundo plano

REPO_DIR="/home/pablo/Programacion/personal/agent-memory-mcp"
PID_FILE="$REPO_DIR/.memory_server.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "ℹ️  No se encontró ningún archivo de PID. ¿El servidor está apagado?"
    exit 0
fi

PID=$(cat "$PID_FILE")

if kill -0 "$PID" 2>/dev/null; then
    echo "🛑 Deteniendo servidor de memoria (PID: $PID)..."
    kill -15 "$PID" # Enviar SIGTERM para cierre ordenado
    
    # Bucle portátil de verificación de detención (hasta 5 intentos)
    STOPPED=0
    for i in 1 2 3 4 5; do
        if ! kill -0 "$PID" 2>/dev/null; then
            STOPPED=1
            break
        fi
        sleep 1
    done
    
    # Forzar si sigue vivo
    if [ $STOPPED -eq 0 ]; then
        echo "⚠️  El proceso no respondió a SIGTERM. Forzando cierre (SIGKILL)..."
        kill -9 "$PID"
    fi
    
    echo "✅ Servidor detenido con éxito."
else
    echo "ℹ️  El proceso $PID ya no está activo."
fi

rm -f "$PID_FILE"
