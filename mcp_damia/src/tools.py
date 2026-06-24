"""
Logique metier des outils MCP : requetes DuckDB + formatage.
Separe du serveur pour etre testable independamment.

CORRECTIONS / OPTIMISATIONS :
  - Routage des postes DATA-DRIVEN depuis le dictionnaire (champ `synonymes` + `filtre`)
    au lieu d'une liste codee en dur -> le dictionnaire est la SOURCE UNIQUE de verite.
    Modifier le JSON modifie desormais reellement le comportement.
  - Refus hors-perimetre et message AMC tires du dictionnaire (reponses_specialisees).
  - Connexion DuckDB persistante (read-only) reutilisee -> plus rapide qu'une
    ouverture/fermeture a chaque requete.
"""
import sys
import json
import unicodedata
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import duckdb
from config.config import CHEMIN_DB, CHEMIN_DICO, MESURES

# --- Dictionnaire charge une fois ---
with open(CHEMIN_DICO, encoding="utf-8") as f:
    DICO = json.load(f)


# --- Connexion DuckDB persistante (read-only), ouverte paresseusement ---
_CON = None
def _connexion():
    global _CON
    if _CON is None:
        _CON = duckdb.connect(str(CHEMIN_DB), read_only=True)
    return _CON


def _sans_accent(s):
    return ''.join(c for c in unicodedata.normalize('NFD', str(s))
                   if unicodedata.category(c) != 'Mn').lower().strip()


# ---------------------------------------------------------------------------
# Routage des postes construit À PARTIR DU DICTIONNAIRE (source unique)
# ---------------------------------------------------------------------------
def _construire_routes():
    """Construit la table de routage poste -> (colonne, valeur) depuis le dico.
    Chaque poste fournit ses `synonymes` et son `filtre` {colonne, valeur}.
    La cle du poste elle-meme sert aussi de synonyme."""
    routes = []
    for nom, conf in DICO.get("postes", {}).items():
        if not isinstance(conf, dict) or "filtre" not in conf:
            continue
        cles = [nom] + list(conf.get("synonymes", []))
        cles_norm = [_sans_accent(c) for c in cles if c]
        col = conf["filtre"]["colonne"]
        val = conf["filtre"]["valeur"]
        routes.append((cles_norm, col, val))
    return routes

_ROUTES = _construire_routes()
_MOTS_EXCLUS = [_sans_accent(m) for m in DICO.get("hors_perimetre", {}).get("mots_exclus", [])]
_MOTS_AMC = [_sans_accent(m) for m in DICO.get("hors_perimetre", {}).get("mots_amc", [])]


def _clause_poste(poste):
    """Renvoie (fragment_sql, params, reconnu).
    reconnu=False -> poste hors perimetre : il faut REFUSER (anti-hallucination)."""
    p = _sans_accent(poste)
    # 1) exclusions explicites (esthetique, confort, AMC...) -> refus
    if any(m in p for m in _MOTS_EXCLUS) or any(m in p for m in _MOTS_AMC):
        return (None, [], False)
    # 2) routage depuis le dico
    for cles_norm, col, val in _ROUTES:
        if any(c in p for c in cles_norm):
            return (f"p.{col} = ?", [val], True)
    # 3) inconnu -> on ne devine pas
    return (None, [], False)


def _message_refus(poste):
    """Message de refus adapte : specialise pour l'AMC, generique sinon.
    Les textes viennent du dictionnaire (reponses_specialisees)."""
    p = _sans_accent(poste)
    rs = DICO.get("hors_perimetre", {}).get("reponses_specialisees", {})
    if any(m in p for m in _MOTS_AMC) and "amc_mutuelle" in rs:
        return rs["amc_mutuelle"]
    return (f"Le poste « {poste} » ne fait pas partie du périmètre Open DAMIR "
            f"(soins remboursés par l'Assurance Maladie, 2022-2025). "
            f"Aucune donnée disponible — je ne peux pas avancer de chiffre.")


def _normaliser_mesure(mesure):
    """Tolere les variantes du LLM : 's' final, accents, casse, synonymes."""
    m = _sans_accent(mesure).rstrip('s')
    SYN = {
        "montant rembourse": "montant_rembourse", "montant_rembourse": "montant_rembourse",
        "rembourse": "montant_rembourse", "remboursement": "montant_rembourse",
        "depense engagee": "depense_engagee", "depense_engagee": "depense_engagee",
        "depense": "depense_engagee", "paiement": "depense_engagee",
        "nombre acte": "nombre_actes", "nombre_acte": "nombre_actes", "acte": "nombre_actes",
        "base remboursement": "base_remboursement", "base_remboursement": "base_remboursement",
        "base": "base_remboursement",
        "depassement": "depassement", "depassement honoraire": "depassement",
    }
    if m in SYN:
        return SYN[m]
    for cle in MESURES:
        if _sans_accent(cle).rstrip('s') == m:
            return cle
    return None


def query_depenses(mesure="montant_rembourse", poste=None, annee=None,
                   region=None, age=None, sexe=None):
    """Calcule une mesure avec filtres optionnels."""
    mesure_canon = _normaliser_mesure(mesure)
    if mesure_canon is None:
        return f"Mesure inconnue. Disponibles : {', '.join(MESURES)}"
    mesure = mesure_canon
    col = MESURES[mesure]
    where, params = [], []
    if annee is not None:
        if isinstance(annee, (list, tuple)):
            annee = annee[0] if annee else None
        if annee is not None:
            where.append("f.soi_ann = ?"); params.append(int(annee))
    poste_refuse = False
    if poste is not None:
        frag, p_params, reconnu = _clause_poste(poste)
        if not reconnu:
            poste_refuse = True
        else:
            where.append(frag); params += p_params
    if region is not None:
        where.append("f.ben_res_reg = ?"); params.append(region)
    if age is not None:
        where.append("f.age_ben_snds = ?"); params.append(age)
    if sexe is not None:
        where.append("f.ben_sex_cod = ?"); params.append(sexe)
    if poste_refuse:
        return _message_refus(poste)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f'''SELECT SUM(f."{col}") FROM faits f
            JOIN prestations p
              ON CAST(f.prs_nat AS VARCHAR) = CAST(p.prs_nat AS VARCHAR)
            {clause}'''
    res = _connexion().execute(sql, params).fetchone()
    val = res[0] if res and res[0] is not None else 0
    label = DICO["mesures"].get(mesure, {}).get("label", mesure)
    return _formater(val, mesure, label)


def _formater(val, mesure, label):
    val = val or 0
    if mesure == "nombre_actes":
        return f"{label} : {val:,.0f} actes".replace(",", " ")
    if abs(val) >= 1e9:
        return f"{label} : {val/1e9:.2f} Md EUR"
    if abs(val) >= 1e6:
        return f"{label} : {val/1e6:.2f} M EUR"
    return f"{label} : {val:,.2f} EUR".replace(",", " ")


def _valeur_brute(mesure_col, poste, annee):
    """Valeur numerique brute, ou None si poste hors perimetre."""
    where, params = [], []
    if annee is not None:
        where.append("f.soi_ann = ?"); params.append(int(annee))
    if poste is not None:
        frag, p_params, reconnu = _clause_poste(poste)
        if not reconnu:
            return None
        where.append(frag); params += p_params
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f'''SELECT SUM(f."{mesure_col}") FROM faits f
            JOIN prestations p ON CAST(f.prs_nat AS VARCHAR)=CAST(p.prs_nat AS VARCHAR)
            {clause}'''
    res = _connexion().execute(sql, params).fetchone()
    return res[0] if res and res[0] is not None else 0


def compare_periods(poste=None, annee1=None, annee2=None, mesure="montant_rembourse"):
    """Compare une mesure entre deux annees, evolution en % et valeur."""
    mc = _normaliser_mesure(mesure)
    if mc is None:
        return f"Mesure inconnue. Disponibles : {', '.join(MESURES)}"
    col = MESURES[mc]
    label = DICO["mesures"].get(mc, {}).get("label", mc)
    if annee1 is None or annee2 is None:
        return "Il faut deux annees a comparer (annee1 et annee2)."
    v1 = _valeur_brute(col, poste, annee1)
    v2 = _valeur_brute(col, poste, annee2)
    if v1 is None or v2 is None:
        return _message_refus(poste) + " Comparaison impossible."

    def fmt(v):
        if mc == "nombre_actes":
            return f"{v:,.0f} actes".replace(",", " ")
        if abs(v) >= 1e9: return f"{v/1e9:.2f} Md EUR"
        if abs(v) >= 1e6: return f"{v/1e6:.2f} M EUR"
        return f"{v:,.2f} EUR".replace(",", " ")

    poste_txt = f" ({poste})" if poste else ""
    if v1 and v1 != 0:
        evol = (v2 - v1) / v1 * 100
        sens = "hausse" if evol >= 0 else "baisse"
        return (f"{label}{poste_txt} : {annee1} = {fmt(v1)}, {annee2} = {fmt(v2)}. "
                f"Evolution : {evol:+.1f}% ({sens}).")
    return f"{label}{poste_txt} : {annee1} = {fmt(v1)}, {annee2} = {fmt(v2)}."


def get_dictionnaire(terme):
    """Renvoie la definition d'un terme metier."""
    t = terme.lower().strip()
    for section in ("mesures", "dimensions", "postes"):
        for cle, c in DICO.get(section, {}).items():
            if not isinstance(c, dict):
                continue
            if t in cle.lower() or t in str(c.get("label", "")).lower():
                return f"{c.get('label', cle)} : {c.get('definition') or c.get('note', '')}"
    return f"Terme '{terme}' non trouve dans le dictionnaire."


def list_valeurs(dimension):
    """Liste les valeurs possibles d'une dimension."""
    d = dimension.lower().strip()
    if d == "poste":
        m = DICO.get("classification_postes", {}).get("macro_categories", {})
        return "Postes : " + " | ".join(m.keys())
    if d in ("region", "age", "sexe"):
        v = DICO.get("dimensions", {}).get(d, {}).get("valeurs_disponibles", {})
        if isinstance(v, dict):
            return f"{d} : " + ", ".join(str(x) for x in v.values())
    if d.startswith("ann"):
        return "Annees : 2022, 2023, 2024, 2025"
    return f"Dimension '{dimension}' inconnue."