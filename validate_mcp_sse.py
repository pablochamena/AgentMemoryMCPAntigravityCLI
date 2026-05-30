#!/usr/bin/env python3
import asyncio
import os
import sys
from pathlib import Path

# Ajustar sys.path para usar el venv local
REPO_DIR = Path(__file__).parent
VENV_SITE = REPO_DIR / "venv" / "lib"
if VENV_SITE.exists():
    import glob
    for sp in glob.glob(str(VENV_SITE / "python3.*" / "site-packages")):
        sys.path.insert(0, sp)
        break
sys.path.insert(0, str(REPO_DIR))

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

async def main():
    port = os.environ.get("MEMORY_PORT", "8009")
    print(f"Testing connection to http://localhost:{port}/mcp using streamable_http_client...")
    async with streamable_http_client(f"http://localhost:{port}/mcp") as (read_stream, write_stream, get_session_id):
        async with ClientSession(read_stream, write_stream) as session:
            # Inicializar sesión
            print("Initializing session...")
            await session.initialize()
            
            # Listar herramientas para verificar qué nombre tienen
            print("\nListing available tools:")
            tools_resp = await session.list_tools()
            for tool in tools_resp.tools:
                print(f" - {tool.name}: {tool.description}")
            
            # 1. Recuerda la información solicitada
            print("\n1. Invoking 'remember' tool...")
            remember_args = {
                "title": "Automatización de Memoria del Agente",
                "summary": "Se implementó y probó con éxito el sistema de automatización de memoria mediante el servidor local MCP HTTP de memoria, facilitando la persistencia y recuperación semántica de contexto.",
                "lesson": "Iniciar el servidor de memoria y usar clientes HTTP compatibles con FastMCP/streamable-http garantiza una memoria persistente robusta en el agente.",
                "tags": ["automatizacion", "mcp", "memoria", "prueba"]
            }
            
            res_remember = await session.call_tool("remember", remember_args)
            print("Response from 'remember':")
            print(res_remember.content[0].text)
            
            # 2. Recupera el recuerdo guardado con recall
            print("\n2. Invoking 'recall' tool...")
            recall_args = {
                "query": "automatización sistema memoria agente",
                "n": 3
            }
            res_recall = await session.call_tool("recall", recall_args)
            print("Response from 'recall':")
            for content in res_recall.content:
                print(content.text)

if __name__ == "__main__":
    asyncio.run(main())
