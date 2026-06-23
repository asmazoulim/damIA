"""
Serveur MCP DAMIA : expose les outils metier (outils.py) via le protocole MCP.
Utilise par un client MCP compatible.
Pour Ollama (qui ne parle pas MCP nativement), voir client_ollama.py.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.server.fastmcp import FastMCP
from src import tools

mcp = FastMCP("DAMIA")


@mcp.tool()
def query_depenses(mesure: str = "montant_rembourse", poste: str | None = None,
                   annee: int | None = None, region: str | None = None,
                   age: str | None = None, sexe: str | None = None) -> str:
    """Calcule une mesure (montant_rembourse, depense_engagee, nombre_actes)
    avec filtres optionnels poste/annee/region/age/sexe."""
    return tools.query_depenses(mesure, poste, annee, region, age, sexe)


@mcp.tool()
def get_dictionnaire(terme: str) -> str:
    """Renvoie la definition d'un terme metier DAMIR."""
    return tools.get_dictionnaire(terme)


@mcp.tool()
def list_valeurs(dimension: str) -> str:
    """Liste les valeurs possibles d'une dimension (poste, region, age, sexe, annee)."""
    return tools.list_valeurs(dimension)


@mcp.tool()
def compare_periods(annee1: int, annee2: int, poste: str | None = None,
                    mesure: str = "montant_rembourse") -> str:
    """Compare une mesure entre deux annees (evolution en %)."""
    return tools.compare_periods(poste, annee1, annee2, mesure)


if __name__ == "__main__":
    mcp.run()