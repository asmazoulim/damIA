"""
src/mcp_client.py — Client MCP persistant a interface SYNCHRONE.

Role : c'est LUI qui rend la voie 2 reelle. assistant.py ne touche plus a tools.py ;
il decouvre et appelle les outils UNIQUEMENT via le protocole MCP, en parlant a
mcp_server.py. Preuve d'interoperabilite : si demain un autre client (Claude Desktop)
parle au meme serveur, il obtient les memes outils.

Le client lance le serveur MCP une seule fois (stdio), garde la session ouverte
dans un thread de fond, et expose des methodes synchrones simples :
    - list_tools()           -> liste des outils decouverts (objets Tool)
    - call_tool(nom, params) -> texte resultat
"""
import sys
import asyncio
import threading
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPClient:
    def __init__(self, command=None, args=None):
        # Par defaut : lance ton serveur via "python -m src.mcp_server" a la racine du projet
        racine = Path(__file__).parent.parent
        self._params = StdioServerParameters(
            command=command or sys.executable,
            args=args or ["-m", "src.mcp_server"],
            cwd=str(racine),
        )
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._ready = threading.Event()
        self._erreur = None
        self._session = None
        self._tools = []
        asyncio.run_coroutine_threadsafe(self._connect(), self._loop)
        if not self._ready.wait(timeout=30):
            raise RuntimeError("Le serveur MCP n'a pas demarre dans les temps.")
        if self._erreur:
            raise self._erreur

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _connect(self):
        try:
            self._cm_stdio = stdio_client(self._params)
            read, write = await self._cm_stdio.__aenter__()
            self._cm_session = ClientSession(read, write)
            self._session = await self._cm_session.__aenter__()
            await self._session.initialize()
            res = await self._session.list_tools()
            self._tools = res.tools
        except Exception as e:
            self._erreur = e
        finally:
            self._ready.set()

    def list_tools(self):
        """Renvoie la liste des outils decouverts via MCP (objets avec .name, .description, .inputSchema)."""
        return self._tools

    def call_tool(self, nom, params):
        """Appelle un outil via MCP et renvoie le texte concatene du resultat."""
        fut = asyncio.run_coroutine_threadsafe(
            self._session.call_tool(nom, arguments=params or {}), self._loop)
        res = fut.result(timeout=120)
        return "\n".join(b.text for b in res.content if hasattr(b, "text"))


# Singleton : un seul client par processus (cache naturel pour Streamlit)
_CLIENT = None
def get_mcp_client():
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = MCPClient()
    return _CLIENT


if __name__ == "__main__":
    c = get_mcp_client()
    print("Outils decouverts :", [t.name for t in c.list_tools()])