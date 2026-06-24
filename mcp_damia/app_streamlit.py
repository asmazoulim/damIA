"""
app_streamlit.py — Interface UX (chat) pour la démo MCP DAMIA.

Lancement :
    cd mcp_damia
    pip install streamlit          # si pas déjà fait
    streamlit run app_streamlit.py


================================================================================
 POINT D'INTEGRATION UNIQUE — c'est la SEULE chose à adapter (2 endroits ci-dessous)
================================================================================
"""
import sys
import os
import streamlit as st

# rendre le dossier src/ importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))


try:
    from src.assistant import poser_question as _fonction_reponse   
    _IMPORT_OK = True
    _IMPORT_ERR = None
except Exception as e:                       # noqa: BLE001
    _IMPORT_OK = False
    _IMPORT_ERR = e

    def _fonction_reponse(question):         # repli pour tester l'UI sans le moteur
        return ("[MODE DEMO UI — moteur non branché]\n"
                f"Question reçue : {question}")


# ------------------------------------------------------------------ #
#  (2) ADAPTE LE FORMAT DE RETOUR                                     #
#      Ton client renvoie peut-être juste une string, ou un dict.     #
#      Cette fonction normalise vers un dict standard pour l'affichage.#
#      Si ton retour contient déjà l'outil/params, mappe-les ici pour #
#      profiter du panneau "Détail technique" (très parlant en démo). #
# ------------------------------------------------------------------ #
def interroger(question):
    res = _fonction_reponse(question)

    # Cas 1 : ta fonction renvoie une simple chaîne
    if isinstance(res, str):
        return {"reponse": res, "outil": None, "parametres": None, "hors_perimetre": False}

    # Cas 2 : ta fonction renvoie un dict -> on mappe les clés possibles
    if isinstance(res, dict):
        return {
            "reponse": res.get("reponse") or res.get("answer") or res.get("texte") or str(res),
            "outil": res.get("outil") or res.get("tool") or res.get("outil_appele"),
            "parametres": res.get("parametres") or res.get("params") or res.get("arguments"),
            "hors_perimetre": bool(res.get("hors_perimetre") or res.get("refus")),
        }

    # Cas 3 : tuple (reponse, outil, params) — adapte si besoin
    if isinstance(res, (list, tuple)):
        reponse = res[0] if len(res) > 0 else ""
        outil = res[1] if len(res) > 1 else None
        params = res[2] if len(res) > 2 else None
        return {"reponse": reponse, "outil": outil, "parametres": params, "hors_perimetre": False}

    return {"reponse": str(res), "outil": None, "parametres": None, "hors_perimetre": False}

# ================================================================================
#  A partir d'ici, rien à changer : c'est l'interface.
# ================================================================================

VIOLET = "#5B2D82"
BLEU = "#1E3A6E"
TURQUOISE = "#00857C"

st.set_page_config(page_title="Assistant Open DAMIR — IA souveraine",
                   page_icon="🩺", layout="centered")

st.markdown(f"""
<style>
  .bandeau {{
     background: linear-gradient(90deg, {VIOLET} 0%, {BLEU} 100%);
     padding: 18px 22px; border-radius: 12px; margin-bottom: 8px;
  }}
  .bandeau h1 {{ color:#fff; margin:0; font-size:1.35rem; font-weight:600; }}
  .bandeau p {{ color:#E6E1F0; margin:4px 0 0; font-size:0.9rem; }}
  .pastille {{
     display:inline-block; background:{TURQUOISE}; color:#fff;
     padding:3px 10px; border-radius:20px; font-size:0.75rem; margin-right:6px;
  }}
  .outil-box {{ font-family:monospace; font-size:0.85rem; }}
</style>
<div class="bandeau">
  <h1>Assistant Open DAMIR — interrogez les données en langage naturel</h1>
  <p><span class="pastille">100% local</span><span class="pastille">souverain</span>
     Aucune donnée ne quitte le poste. Le modèle propose, le code valide et ne ment jamais.</p>
</div>
""", unsafe_allow_html=True)

# --- Barre latérale : contexte + transparence (parle bien à une direction) ---
with st.sidebar:
    st.subheader("À propos de la démo")
    st.markdown(
        "- **Modèle** : qwen2.5:7b (Ollama, local)\n"
        "- **Données** : Open DAMIR 2022-2025\n"
        "- **Moteur** : 4 outils paramétrés + dictionnaire métier\n"
        "- **Principe** : pas de SQL libre. Le LLM choisit un outil, "
        "le code exécute la requête sur DuckDB."
    )
    st.divider()
    st.caption("Le panneau « Détail technique » sous chaque réponse montre "
               "quel outil a été appelé et avec quels paramètres — "
               "preuve que le chiffre vient des données, pas du modèle.")
    if not _IMPORT_OK:
        st.warning("Moteur non branché : adapte la ligne d'import (1) dans "
                   f"app_streamlit.py.\n\nDétail : {_IMPORT_ERR}")

# --- Questions de démo prêtes à cliquer (évite de taper en live) ---
QUESTIONS_DEMO = [
    "Quel est le montant remboursé par l'AM en 2023 ?",
    "Combien pour l'optique en 2023 ?",
    "Compare les dépenses dentaires entre 2022 et 2024",
    "Combien a coûté la chirurgie esthétique ?",   # -> doit refuser proprement
]

st.write("**Questions de démonstration :**")
cols = st.columns(2)
question_cliquee = None
for i, q in enumerate(QUESTIONS_DEMO):
    if cols[i % 2].button(q, key=f"demo_{i}", use_container_width=True):
        question_cliquee = q

# --- Historique de conversation ---
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("detail"):
            with st.expander("Détail technique"):
                d = msg["detail"]
                if d.get("outil"):
                    st.markdown(f"**Outil appelé :** `{d['outil']}`")
                if d.get("parametres"):
                    st.markdown("**Paramètres :**")
                    st.json(d["parametres"])
                if d.get("hors_perimetre"):
                    st.info("Demande hors périmètre — refus volontaire, "
                            "aucune valeur inventée.")


def _traiter(question):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("Le modèle choisit un outil, le code interroge la base…"):
            res = interroger(question)
        st.markdown(res["reponse"])
        if res.get("outil") or res.get("hors_perimetre"):
            with st.expander("Détail technique"):
                if res.get("outil"):
                    st.markdown(f"**Outil appelé :** `{res['outil']}`")
                if res.get("parametres"):
                    st.markdown("**Paramètres :**")
                    st.json(res["parametres"])
                if res.get("hors_perimetre"):
                    st.info("Demande hors périmètre — refus volontaire, "
                            "aucune valeur inventée.")
    st.session_state.messages.append(
        {"role": "assistant", "content": res["reponse"], "detail": res})


# --- Entrées : bouton de démo OU champ de saisie ---
question_saisie = st.chat_input("Posez votre question sur les données Open DAMIR…")

if question_cliquee:
    _traiter(question_cliquee)
elif question_saisie:
    _traiter(question_saisie)