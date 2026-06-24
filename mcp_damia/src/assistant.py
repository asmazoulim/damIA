"""
assistant.py — Orchestrateur multi-modèle de l'assistant DAMIA (option B).

Principe (inchangé) : le LLM PROPOSE un outil, le CODE dispose et exécute.
Différence avec ollama_client.py : on ne dépend plus du tool-calling NATIF d'Ollama.
On décrit les outils dans le PROMPT, le modèle répond en JSON, on parse, on exécute.
=> portable sur n'importe quel backend (Ollama, Transformers, API) via backends.py.

Usage :
    from src.assistant import poser_question
    res = poser_question("Combien pour l'optique en 2023 ?")
    # res = {"reponse": "...", "outil": "...", "parametres": {...}}
"""
import sys
import json
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src import tools
from src.backends import get_backend

# Mapping nom d'outil -> fonction Python (identique à ollama_client.py)
FONCTIONS = {
    "query_depenses": tools.query_depenses,
    "get_dictionnaire": tools.get_dictionnaire,
    "list_valeurs": tools.list_valeurs,
    "compare_periods": tools.compare_periods,
}

# Description des outils, injectée dans le prompt (remplace tools=... du natif)
DESCRIPTION_OUTILS = """\
Tu disposes de 4 outils pour interroger les données Open DAMIR (dépenses Assurance
Maladie 2022-2025). Tu dois OBLIGATOIREMENT choisir un outil pour répondre à une
question sur les données. Tu n'as pas le droit d'inventer un chiffre.

Outils disponibles :
1. query_depenses(mesure, poste, annee, region, age, sexe)
   - mesure : "montant_rembourse" (défaut), "depense_engagee" ou "nombre_actes"
   - poste : ex "optique", "dentaire", "pharmacie", "audio", "hospitalisation"
   - annee : un entier (ex 2023). Filtres optionnels : region, age, sexe.
2. compare_periods(annee1, annee2, poste, mesure)
   - pour comparer une mesure entre DEUX années (évolution).
3. get_dictionnaire(terme)
   - pour définir un terme métier.
4. list_valeurs(dimension)
   - pour lister les valeurs d'une dimension (poste, region, age, sexe, annee).

Règles :
- Paramètres TOUJOURS en français ('dentaire' pas 'dental').
- Mesure par défaut : "montant_rembourse".
- Si la question sort du périmètre (donnée non disponible), choisis l'outil le plus
  proche quand même : le code refusera proprement. N'invente jamais.
"""

# Le format de sortie imposé au modèle
INSTRUCTION_JSON = """\
Réponds UNIQUEMENT par un objet JSON, sans aucun texte autour, sans balise de code.
Format EXACT :
{"outil": "<nom_outil>", "parametres": {<clés:valeurs>}}

Exemples :
Question : "Combien pour l'optique en 2023 ?"
{"outil": "query_depenses", "parametres": {"mesure": "montant_rembourse", "poste": "optique", "annee": 2023}}

Question : "Compare le dentaire entre 2022 et 2024"
{"outil": "compare_periods", "parametres": {"annee1": 2022, "annee2": 2024, "poste": "dentaire"}}
"""


def _construire_prompt(question):
    return (f"{DESCRIPTION_OUTILS}\n{INSTRUCTION_JSON}\n\n"
            f"Question : \"{question}\"\n")


def _extraire_json(texte):
    """Parseur ROBUSTE : récupère le 1er objet JSON même noyé dans du texte
    ou entouré de ```json ... ```. Renvoie un dict, ou None si introuvable."""
    if not texte:
        return None
    # 1) tentative directe
    try:
        return json.loads(texte.strip())
    except json.JSONDecodeError:
        pass
    # 2) enlever les balises de code éventuelles
    nettoye = re.sub(r"```(?:json)?", "", texte).strip()
    try:
        return json.loads(nettoye)
    except json.JSONDecodeError:
        pass
    # 3) extraire le premier bloc { ... } équilibré
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
                fragment = nettoye[debut:i + 1]
                try:
                    return json.loads(fragment)
                except json.JSONDecodeError:
                    return None
    return None


def _reformuler(resultat_outil):
    """Reformule la réponse finale EN PYTHON (pas de 2e appel LLM).
    tools.py renvoie déjà une phrase formatée et fiable -> on la rend telle quelle.
    C'est plus rapide et zéro risque que le modèle déforme le chiffre."""
    return str(resultat_outil)


def poser_question(question):
    """Point d'entrée unique. Renvoie {reponse, outil, parametres} —
    même format que ollama_client.py, donc l'app Streamlit n'a rien à changer."""
    backend = get_backend()
    prompt = _construire_prompt(question)

    # 1) le LLM propose (texte) -> on parse le JSON
    texte = backend.generer(prompt)
    choix = _extraire_json(texte)

    # 2) garde-fou : JSON illisible ou outil inconnu -> refus propre, pas d'invention
    if not choix or "outil" not in choix:
        return {"reponse": "Je n'ai pas pu interpréter cette question dans mon périmètre "
                           "(données Open DAMIR 2022-2025). Pouvez-vous la reformuler ?",
                "outil": None, "parametres": None}

    nom = choix.get("outil")
    params = choix.get("parametres", {}) or {}
    if nom not in FONCTIONS:
        return {"reponse": f"Aucun outil disponible pour traiter « {question} » dans le "
                           "périmètre Open DAMIR.", "outil": nom, "parametres": params}

    # 3) le CODE dispose : exécution validée (tools.py gère déjà les refus hors périmètre)
    try:
        resultat = FONCTIONS[nom](**params)
    except TypeError as e:
        # paramètres mal formés par le modèle -> on ne plante pas, on refuse proprement
        return {"reponse": "Les paramètres proposés n'étaient pas valides. Reformulez la question ?",
                "outil": nom, "parametres": params}

    return {"reponse": _reformuler(resultat), "outil": nom, "parametres": params}


if __name__ == "__main__":
    print("=== Assistant DAMIA multi-modèle (Ctrl+C pour quitter) ===")
    print(f"Backend : {get_backend().__class__.__name__}")
    while True:
        try:
            q = input("\nQuestion > ")
            if not q.strip():
                continue
            r = poser_question(q)
            print(r["reponse"])
            if r["outil"]:
                print(f"   [outil: {r['outil']} | params: {r['parametres']}]")
        except (KeyboardInterrupt, EOFError):
            print("\nAu revoir.")
            break
