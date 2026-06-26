"""
Serveur MCP DAMIA — version DÉPLOYABLE (transport HTTP, model-agnostic).

Différence avec la version locale (stdio) : ce serveur écoute en HTTP, donc
N'IMPORTE QUEL client MCP compatible peut s'y connecter à distance, avec SON
PROPRE modèle. Le serveur n'embarque aucun LLM : il n'expose que des outils.

Les docstrings des outils ci-dessous sont LUES par le client/modèle pour décider
quel outil appeler : elles doivent rester claires et précises.

Lancement :
    python src/mcp_server.py
Variables d'environnement :
    MCP_HOST (défaut 0.0.0.0), MCP_PORT (défaut 7860)
Endpoint exposé : http://<hote>:<port>/mcp   (transport streamable-http)
"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.server.fastmcp import FastMCP
from src import tools

HOST = os.environ.get("MCP_HOST", "0.0.0.0")
PORT = int(os.environ.get("MCP_PORT", "7860"))

mcp = FastMCP("DAMIA", host=HOST, port=PORT)


# --------------------------------------------------------------------------
# Outils existants
# --------------------------------------------------------------------------
@mcp.tool()
def query_depenses(mesure: str = "montant_rembourse", poste: str | None = None,
                   annee: int | None = None, region: str | None = None,
                   age: str | None = None, sexe: str | None = None) -> str:
    """Calcule une mesure de dépense de santé (Open DAMIR, données AMO).
    mesure : 'montant_rembourse' (défaut), 'depense_engagee' ou 'nombre_actes'.
    poste : ex 'optique', 'dentaire', 'pharmacie', 'hospitalisation', 'audio'.
    Filtres optionnels : annee (ex 2023), region, age, sexe.
    Hors périmètre (AMC/mutuelle, esthétique) -> refus propre, pas d'invention."""
    return tools.query_depenses(mesure, poste, annee, region, age, sexe)


@mcp.tool()
def compare_periods(annee1: int, annee2: int, poste: str | None = None,
                    mesure: str = "montant_rembourse") -> str:
    """Compare une mesure entre DEUX années et calcule l'évolution en %.
    À utiliser pour toute question de comparaison ou d'évolution entre deux années."""
    return tools.compare_periods(poste, annee1, annee2, mesure)


@mcp.tool()
def get_dictionnaire(terme: str) -> str:
    """Renvoie la définition d'un terme métier DAMIR (mesure, dimension, poste, panier)."""
    return tools.get_dictionnaire(terme)


@mcp.tool()
def list_valeurs(dimension: str) -> str:
    """Liste les valeurs possibles d'une dimension : poste, region, age, sexe ou annee."""
    return tools.list_valeurs(dimension)


# --------------------------------------------------------------------------
# Nouveaux outils (extension CETAS)
# --------------------------------------------------------------------------
@mcp.tool()
def top_postes(mesure: str = "montant_rembourse", annee: int | None = None, n: int = 5) -> str:
    """Classement des postes de soin par mesure (top N).
    Pour les questions du type 'quels sont les postes qui coûtent le plus', 'top 5 postes'."""
    return tools.top_postes(mesure, annee, n)


@mcp.tool()
def repartition(mesure: str = "montant_rembourse", dimension: str = "poste",
                annee: int | None = None, poste: str | None = None) -> str:
    """Ventile une mesure selon une dimension : 'poste', 'region', 'age' ou 'sexe'.
    Pour 'comment se répartit X par région / par âge / par poste'."""
    return tools.repartition(mesure, dimension, annee, poste)


@mcp.tool()
def evolution_serie(mesure: str = "montant_rembourse", poste: str | None = None) -> str:
    """Série temporelle d'une mesure sur toutes les années disponibles.
    Pour 'montre l'évolution de X sur la période', 'tendance de X'."""
    return tools.evolution_serie(mesure, poste)


if __name__ == "__main__":
    # transport HTTP (streamable-http) -> accessible par tout client MCP distant
    mcp.run(transport="streamable-http")