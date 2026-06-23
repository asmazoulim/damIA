"""
Logique metier des outils MCP : requetes DuckDB + formatage.
Separe du serveur pour etre testable independamment.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import duckdb
from config.config import CHEMIN_DB, CHEMIN_DICO, MESURES

# Charger le dictionnaire une fois
with open(CHEMIN_DICO, encoding="utf-8") as f:
    DICO = json.load(f)


def _connexion():
    return duckdb.connect(str(CHEMIN_DB), read_only=True)


def _sans_accent(s):
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFD', str(s))
                   if unicodedata.category(c) != 'Mn').lower().strip()


def _clause_poste(poste):
    """Renvoie (fragment_sql, params, reconnu).
    reconnu=True si le poste correspond a un poste connu du perimetre.
    reconnu=False -> le poste n'existe pas dans les donnees : il faut REFUSER
    plutot que d'inventer une correspondance (anti-hallucination).
    Detecte FR + EN (le petit LLM traduit parfois)."""
    p = _sans_accent(poste)
    # Termes a EXCLURE explicitement : hors perimetre AMO (non rembourses)
    HORS_PERIMETRE = ["esthetique", "esthetic", "cosmetic", "confort"]
    if any(h in p for h in HORS_PERIMETRE):
        return (None, [], False)   # refus : hors perimetre

    # Mots-cles precis -> (colonne, valeur). Pas de terme trop large isole.
    MOTS = [
        (["optique", "optical", "lunette", "verre correcteur"],
            ("sous_categorie_cor", "Optique Médicale")),
        (["audioprothese", "audio", "auditi", "hearing"],
            ("sous_categorie_cor", "Audioprothèse")),
        (["dentaire", "dental", "orthodont", "teeth", "dent "],
            ("macro_categorie", "Soins Dentaires & Orthodontie")),
        (["pharmaci", "pharmacy", "medicament"],
            ("macro_categorie", "Pharmacie")),
        (["hospitalisation", "hospital", "chirurgie hospitaliere"],
            ("macro_categorie", "Hospitalisation & Chirurgie")),
        (["imagerie", "imaging", "radiolog"],
            ("macro_categorie", "Imagerie & Radiologie")),
    ]
    for cles, (colonne, valeur) in MOTS:
        if any(c in p for c in cles):
            return (f"p.{colonne} = ?", [valeur], True)

    # Poste non reconnu : on NE devine PAS. Signal de refus.
    return (None, [], False)


def _normaliser_mesure(mesure):
    """Tolere les variantes du LLM : 's' final, accents, casse, synonymes.
    Renvoie la cle exacte de MESURES, ou None si vraiment introuvable."""
    import unicodedata
    def sa(s):
        return ''.join(c for c in unicodedata.normalize('NFD', str(s))
                       if unicodedata.category(c) != 'Mn').lower().strip()
    m = sa(mesure).rstrip('s')  # enleve accents/casse + 's' final eventuel
    # Synonymes -> cle canonique
    SYN = {
        "montant rembourse": "montant_rembourse",
        "montant_rembourse": "montant_rembourse",
        "rembourse": "montant_rembourse",
        "remboursement": "montant_rembourse",
        "depense engagee": "depense_engagee",
        "depense_engagee": "depense_engagee",
        "depense": "depense_engagee",
        "paiement": "depense_engagee",
        "nombre acte": "nombre_actes",
        "nombre_acte": "nombre_actes",
        "acte": "nombre_actes",
        "base remboursement": "base_remboursement",
        "base_remboursement": "base_remboursement",
        "base": "base_remboursement",
        "depassement": "depassement",
        "depassement honoraire": "depassement",
    }
    if m in SYN:
        return SYN[m]
    # Tentative directe sur les cles de MESURES (normalisees)
    for cle in MESURES:
        if sa(cle).rstrip('s') == m:
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
        # Robustesse : si le LLM envoie une liste [2022, 2024] par erreur,
        # on prend la 1re annee (pour une vraie comparaison -> compare_periods)
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
        return (f"Le poste « {poste} » ne fait pas partie du périmètre Open DAMIR "
                f"(soins remboursés par l'Assurance Maladie, 2022-2025). "
                f"Aucune donnée disponible — je ne peux pas avancer de chiffre.")
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    # CAST en VARCHAR des deux cotes : prs_nat peut etre lu nombre ici, texte la
    sql = f'''SELECT SUM(f."{col}") FROM faits f
            JOIN prestations p
              ON CAST(f.prs_nat AS VARCHAR) = CAST(p.prs_nat AS VARCHAR)
            {clause}'''
    con = _connexion()
    res = con.execute(sql, params).fetchone()
    con.close()
    val = res[0] if res and res[0] is not None else 0
    label = DICO["mesures"].get(mesure, {}).get("label", mesure)
    return _formater(val, mesure, label)


def _formater(val, mesure, label):
    """Formate une valeur numerique selon la mesure."""
    val = val or 0
    if mesure == "nombre_actes":
        return f"{label} : {val:,.0f} actes".replace(",", " ")
    if abs(val) >= 1e9:
        return f"{label} : {val/1e9:.2f} Md EUR"
    if abs(val) >= 1e6:
        return f"{label} : {val/1e6:.2f} M EUR"
    return f"{label} : {val:,.2f} EUR".replace(",", " ")


def _valeur_brute(mesure_col, poste, annee):
    """Renvoie la valeur numerique brute, ou None si poste hors perimetre."""
    where, params = [], []
    if annee is not None:
        where.append("f.soi_ann = ?"); params.append(int(annee))
    if poste is not None:
        frag, p_params, reconnu = _clause_poste(poste)
        if not reconnu:
            return None   # poste hors perimetre -> signal de refus
        where.append(frag); params += p_params
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f'''SELECT SUM(f."{mesure_col}") FROM faits f
            JOIN prestations p ON CAST(f.prs_nat AS VARCHAR)=CAST(p.prs_nat AS VARCHAR)
            {clause}'''
    con = _connexion()
    res = con.execute(sql, params).fetchone()
    con.close()
    return res[0] if res and res[0] is not None else 0


def compare_periods(poste=None, annee1=None, annee2=None, mesure="montant_rembourse"):
    """Compare une mesure entre deux annees, avec evolution en % et valeur."""
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
        return (f"Le poste « {poste} » ne fait pas partie du périmètre Open DAMIR "
                f"(soins remboursés par l'Assurance Maladie). Comparaison impossible — "
                f"je ne peux pas avancer de chiffre.")

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
            if t in cle.lower() or t in str(c.get("label","")).lower():
                return f"{c.get('label', cle)} : {c.get('definition') or c.get('note','')}"
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