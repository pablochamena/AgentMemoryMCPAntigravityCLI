#!/bin/bash
# start_memory.sh
# Lanza el servidor MCP HTTP de memoria en segundo plano

REPO_DIR="/home/pablo/Programacion/personal/agent-memory-mcp"
PID_FILE="$REPO_DIR/.memory_server.pid"
PORT=${MEMORY_PORT:-8009}
export MEMORY_PORT=$PORT

# Capturar el directorio actual donde el programador ejecutó el comando
# Esto se inyecta al servidor HTTP para mantener la compatibilidad contextual
export MEMORY_CWD=$(pwd)

# Verificar si el servidor ya está activo
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "⚠️  El servidor de memoria ya está corriendo (PID: $PID) en el puerto $PORT."
        exit 0
    fi
    rm -f "$PID_FILE"
fi

# Activar el entorno virtual del proyecto
if [ -d "$REPO_DIR/venv" ]; then
    source "$REPO_DIR/venv/bin/activate"
else
    echo "❌ Error: Entorno virtual no encontrado en $REPO_DIR/venv"
    exit 1
fi

echo "🚀 Iniciando servidor MCP de memoria en segundo plano..."
echo "📂 Contexto de proyecto activo: $MEMORY_CWD"

# Lanzar con nohup redirigiendo logs
nohup python3 "$REPO_DIR/server_http.py" > "$REPO_DIR/server_http.log" 2>&1 &
NEW_PID=$!

# Guardar el PID inmediatamente
echo "$NEW_PID" > "$PID_FILE"

# Bucle portátil y robusto de verificación de arranque (hasta 5 intentos)
echo -n "⏳ Esperando a que el servidor responda..."
STARTED=0
for i in 1 2 3 4 5; do
    sleep 2
    if kill -0 "$NEW_PID" 2>/dev/null; then
        # Intentar conectar al puerto usando curl o nc de forma básica
        if curl -s "http://localhost:$PORT/mcp" > /dev/null 2>&1 || nc -z localhost $PORT >/dev/null 2>&1; then
            STARTED=1
            break
        fi
        echo -n "."
    else
        echo ""
        echo "❌ El proceso terminó prematuramente. Revisa los logs en $REPO_DIR/server_http.log"
        rm -f "$PID_FILE"
        exit 1
    fi
done

echo ""

if [ $STARTED -eq 1 ]; then
    echo "✅ Servidor iniciado correctamente."
    echo "   • PID: $NEW_PID"
    echo "   • Endpoint: http://localhost:$PORT/mcp"
    echo "   • Logs disponibles en: tail -f $REPO_DIR/server_http.log"
else
    echo "⚠️  El servidor se lanzó, pero no respondió en el puerto $PORT después de 10 segundos."
    echo "   Por favor, verifica su estado en: tail -n 20 $REPO_DIR/server_http.log"
fi
