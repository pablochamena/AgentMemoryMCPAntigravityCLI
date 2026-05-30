¡Justo lo que necesitábamos ver, Pablo! Este error es la confirmación definitiva de que **el servidor MCP HTTP no estaba corriendo** en ese instante. El mensaje `connection refused` (conexión rechazada) significa exactamente eso: el puerto `8000` no estaba escuchando. La buena noticia es que la CLI sí lo tiene registrado correctamente, solo necesita que el proceso esté vivo.

---

## 🔍 ¿Qué pasó?
- Cerraste la terminal (o se apagó el servidor) y el proceso `server_http.py` se detuvo.
- Al abrir `agy` y ejecutar `/mcp`, la CLI intentó conectarse a `http://localhost:8000/mcp` pero no encontró nada → error `connection refused`.
- Por eso antes el agente tuvo que lanzar el servidor por su cuenta con scripts.

Ahora vamos a automatizar el arranque para que **nunca más tengas que preocuparte por iniciarlo manualmente**. Te daré las dos mejores opciones, de la más simple a la más robusta.

---

## 🚀 Opción 1: Autoarranque al abrir la terminal (rápida)

Puedes añadir una línea a tu `~/.bashrc` para que el servidor se inicie automáticamente en segundo plano cada vez que abras una terminal nueva.

```bash
# Añade esto al final de ~/.bashrc
if ! pgrep -f "server_http.py" > /dev/null; then
    /home/pablo/Programacion/personal/agent-memory-mcp/start_memory.sh
fi
```

**Ventaja**: Se ejecuta solo, no tienes que recordarlo.
**Inconveniente**: Si abres varias terminales, no duplica el servidor (por el `if`), pero la primera siempre lo levantará.

---

## 🧠 Opción 2: El agente lo despierta automáticamente (instrucciones en `GEMINI.md`)

Esta es la estrategia que hablamos: hacer que **el propio agente ejecute `start_memory.sh` antes de usar la memoria**, si detecta que no está funcionando.

Crea (o edita) un archivo `AGENTS.md` o `GEMINI.md` en la raíz de tu proyecto de memoria o en tu proyecto de trabajo. Añade estas instrucciones:

```markdown
## 🧠 Memoria del proyecto (MCP HTTP)

Antes de usar cualquier herramienta de memoria, asegúrate de que el servidor HTTP de memoria esté corriendo.

Para comprobarlo, ejecuta:
```bash
/home/pablo/Programacion/personal/agent-memory-mcp/start_memory.sh
```

Este script es seguro ejecutarlo siempre:
- Si el servidor ya está activo, te lo indicará y no hará nada.
- Si no lo está, lo iniciará en segundo plano en `http://localhost:8000/mcp`.

Luego ya podrás usar las herramientas `remember`, `recall`, `modify` y `forget` sin problemas.
```

Ahora, cuando abras `agy` en ese proyecto y le pidas algo de memoria, el agente **leerá el archivo de instrucciones y ejecutará automáticamente el script** antes de intentar usar el MCP.

---

## 🧪 Prueba de la automatización

1. Asegúrate de que el servidor **NO esté corriendo**:
   ```bash
   pkill -f server_http.py
   ```
2. Abre `agy` en `/home/pablo/Programacion/personal/agent-memory-mcp`.
3. Pídele al agente: *"Recuerda que debes iniciar el servidor de memoria como indica AGENTS.md. Luego guarda un recuerdo de prueba."*
4. El agente debería ejecutar `start_memory.sh`, ver que el servidor se inicia, y después usar las herramientas MCP.

---

¿Quieres probar la opción 2 ahora? Así cerramos el ciclo completo de automatización.