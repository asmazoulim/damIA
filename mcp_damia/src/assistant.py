"""
src/assistant.py — Orchestrateur multi-modele, client MCP (VOIE 2).

CHANGEMENT CLE vs version precedente :
  - NE FAIT PLUS "from src import tools" ni FONCTIONS = {...}.
  - Decouvre les outils DYNAMIQUEMENT via le protocole MCP (mcp_client).
  - Construit la description des outils pour le prompt A PARTIR de cette decouverte.
  => Les appels passent reellement par MCP : c'est la preuve d'interoperabilite.

Le modele (Qwen/Ollama via backends.py) PROPOSE un outil en JSON ; le code l'appelle
via MCP. Si demain Claude Desktop parle au meme serveur, il voit les memes outils.

Usage :
    from src.assistant import poser_question
    res = poser_question("Taux de couverture de l'optique en 2023 ?")
"""
import sys
import json
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.backends import get_backend
from src.mcp_client import get_mcp_client


INSTRUCTION_JSON = """\
Reponds UNIQUEMENT par un objet JSON, sans aucun texte autour, sans balise de code.
Format EXACT :
{"outil": "<nom_outil>", "parametres": {<cles:valeurs>}}

Regles :
- Parametres TOUJOURS en francais ('dentaire' pas 'dental', 'optique' pas 'optical').
- Choisis un seul outil. N'invente jamais de chiffre.
"""


def _decrire_outils(tools):
    """Construit la description injectee au prompt A PARTIR des outils MCP decouverts."""
    lignes = ["Tu disposes des outils suivants pour interroger les donnees Open DAMIR "
              "(depenses Assurance Maladie 2022-2025). Choisis OBLIGATOIREMENT un outil.\n"]
    for t in tools:
        props = (t.inputSchema or {}).get("properties", {})
        params = ", ".join(props.keys()) if props else "(aucun)"
        lignes.append(f"- {t.name}({params}) : {t.description}")
    return "\n".join(lignes)


def _construire_prompt(question, description_outils):
    return (f"{description_outils}\n\n{INSTRUCTION_JSON}\n\n"
            f'Question : "{question}"\n')


def _extraire_json(texte):
    """Parseur robuste : recupere le 1er objet JSON meme noye dans du texte."""
    if not texte:
        return None
    try:
        return json.loads(texte.strip())
    except json.JSONDecodeError:
        pass
    nettoye = re.sub(r"```(?:json)?", "", texte).strip()
    try:
        return json.loads(nettoye)
    except json.JSONDecodeError:
        pass
    debut = nettoye.find("{")
    if debut == -1:
        return None
    profondeur = 0
    for i in range(debut, len(nettoye)):
        if nettoye[i] == "{":
            profondeur += 1
        elif nettoye[i] == "}":
            profondeur -= 1
            if profondeur == 0:
                try:
                    return json.loads(nettoye[debut:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def poser_question(question):
    """Point d'entree unique. Renvoie {reponse, outil, parametres}.
    Format inchange : l'app Streamlit n'a rien a adapter cote affichage."""
    backend = get_backend()           # cache dans backends.py (charge une fois)
    client = get_mcp_client()         # connexion MCP persistante (lance une fois)

    tools = client.list_tools()
    noms_valides = {t.name for t in tools}
    description = _decrire_outils(tools)

    # 1) le LLM propose (texte) -> JSON
    texte = backend.generer(_construire_prompt(question, description))
    choix = _extraire_json(texte)

    if not choix or "outil" not in choix:
        return {"reponse": "Je n'ai pas pu interpreter cette question dans mon perimetre "
                           "(Open DAMIR 2022-2025). Pouvez-vous la reformuler ?",
                "outil": None, "parametres": None}

    nom = choix.get("outil")
    params = choix.get("parametres", {}) or {}
    if nom not in noms_valides:
        return {"reponse": f"Aucun outil MCP nomme « {nom} » n'est disponible.",
                "outil": nom, "parametres": params}

    # 2) appel via le PROTOCOLE MCP (et non un import Python direct)
    try:
        resultat = client.call_tool(nom, params)
    except Exception as e:
        return {"reponse": "L'appel de l'outil via MCP a echoue. Reformulez la question ?",
                "outil": nom, "parametres": params}

    return {"reponse": str(resultat), "outil": nom, "parametres": params}


if __name__ == "__main__":
    print("=== Assistant DAMIA (client MCP, multi-modele) ===")
    print(f"Backend : {get_backend().__class__.__name__}")
    print("Outils MCP :", [t.name for t in get_mcp_client().list_tools()])
    while True:
        try:
            q = input("\nQuestion > ")
            if not q.strip():
                continue
            r = poser_question(q)
            print(r["reponse"])
            if r["outil"]:
                print(f"   [outil MCP: {r['outil']} | params: {r['parametres']}]")
        except (KeyboardInterrupt, EOFError):
            print("\nAu revoir.")
            break