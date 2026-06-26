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


@st.cache_resource
def _init():
    from src.mcp_client import get_mcp_client
    from src.backends import get_backend
    get_backend(); get_mcp_client()   # force le chargement unique
    return True
_init()

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
     padding: 20px 25px; border-radius: 12px; margin-bottom: 15px;
     box-shadow: 0 4px 6px rgba(0,0,0,0.1);
  }}
  .bandeau h1 {{ color:#ffffff; margin:0; font-size:1.4rem; font-weight:600; letter-spacing: 0.5px; }}
  .bandeau p {{ color:#E6E1F0; margin:8px 0 0; font-size:0.95rem; }}
  .pastille {{
     display:inline-block; background:{TURQUOISE}; color:#ffffff;
     padding:4px 12px; border-radius:20px; font-size:0.8rem; font-weight: bold; margin-right:8px;
  }}
</style>
<div class="bandeau">
  <h1>Assistant Open DAMIR — Démonstrateur MCP</h1>
  <p><span class="pastille">Model-Agnostic</span><span class="pastille">Zéro Hallucination Numérique</span>
     Aucune donnée ne quitte le serveur métier. Le LLM orchestre, le code exécute la requête SQL.</p>
</div>
""", unsafe_allow_html=True)

# --- Barre latérale : contexte + transparence (parle bien à une direction) ---
with st.sidebar:
    st.subheader("Architecture de la démo")
    st.markdown(
        f"- **Protocole** : Standard MCP (Model Context Protocol)\n"
        f"- **Modèle Client** : Agnostique (interchangeable)\n"
        f"- **Données** : Open DAMIR 2022-2025 (DuckDB locale)\n"
        f"- **Moteur** : Dictionnaire métier data-driven"
    )
    st.divider()
    st.caption("Le panneau « 🛠️ Détail technique » sous chaque réponse prouve que le chiffre vient de la base de données, et non des poids du modèle.")
# --- Questions de démo (à cliquer pour tester le moteur) ---
QUESTIONS_DEMO = [
    "Quel est le montant remboursé par l'AM en 2023 ?",
    "Combien pour l'optique en 2023 ?",
    "Quel est le taux de couverture pour l'optique en 2023 ?",
    "Compare les dépenses dentaires entre 2022 et 2024",
    "Combien a coûté la chirurgie esthétique ?",   # -> doit refuser proprement
]
# --- Questions de démo (masquées par défaut pour épurer l'UI) ---
question_cliquee = None
with st.expander("💡 Suggestions de questions pour la démonstration", expanded=False):
    cols = st.columns(2)
    for i, q in enumerate(QUESTIONS_DEMO):
        if cols[i % 2].button(q, key=f"demo_{i}", use_container_width=True):
            question_cliquee = q

# --- Écran d'accueil (affiché uniquement si le chat est vide) ---
if "messages" not in st.session_state or len(st.session_state.messages) == 0:
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("Périmètre des données embarquées")
    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric(label="Période couverte", value="2022 - 2025")
    kpi2.metric(label="Volume de faits", value="~11,8 Millions", delta="Agréments CNAM")
    kpi3.metric(label="Prestations classées", value="1 569", delta="Dictionnaire actif")
    st.markdown("<br><hr>", unsafe_allow_html=True)
    
# --- Historique de conversation ---
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    avatar = "👤" if msg["role"] == "user" else "⚕️"
    with st.chat_message(msg["role"], avatar=avatar):
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
    with st.chat_message("user", avatar="👤"):
        st.markdown(question)
    with st.chat_message("assistant", avatar="⚕️"):
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