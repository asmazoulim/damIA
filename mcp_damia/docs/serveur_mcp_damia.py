"""
=============================================================================
 SERVEUR MCP DAMIA — POC local
=============================================================================
 Expose les données Open DAMIR (réduites 2022-2025) via le protocole MCP.
 Le LLM (via Ollama) choisit un outil et remplit ses paramètres ;
 c'est CE code (Python + DuckDB) qui fait le travail fiable.

 Pas de Text-to-SQL libre : 4 outils à requêtes paramétrées.

 PRÉREQUIS (à installer une fois) :
   pip install "mcp[cli]" duckdb

 FICHIERS attendus dans le même dossier :
   - dictionnaire_semantique_damir.json   (le dictionnaire)
   - damia.duckdb  OU les 3 CSV à charger (voir section CHARGEMENT)

 LANCEMENT :
   python serveur_mcp_damia.py
=============================================================================
"""

import json
import duckdb
from pathlib import Path
from mcp.server.fastmcp import FastMCP

# -----------------------------------------------------------------------------
# CONFIGURATION — adapte ces chemins à ton poste
# -----------------------------------------------------------------------------
DOSSIER = Path(__file__).parent
CHEMIN_DICO = DOSSIER / "dictionnaire_semantique_damir.json"
CHEMIN_DB = DOSSIER / "damia.duckdb"          # base DuckDB (créée au 1er lancement)
CHEMIN_FAITS = DOSSIER / "fact_damir_2022_2025.csv"
CHEMIN_PRESTATIONS = DOSSIER / "dim_prestations.csv"
CHEMIN_ATC = DOSSIER / "correspondance_ATC.csv"

# Noms de colonnes (indicateurs PRÉFILTRÉS FLT_ — déjà filtrés sur prs_rem_typ)
COL_REMBOURSE = "FLT_REM_MNT"
COL_DEPENSE = "FLT_PAI_MNT"
COL_ACTES = "FLT_ACT_QTE"

# Mapping mesure -> colonne (le LLM utilise le nom "métier", pas la colonne)
MESURES = {
    "montant_rembourse": COL_REMBOURSE,
    "depense_engagee": COL_DEPENSE,
    "nombre_actes": COL_ACTES,
}

# -----------------------------------------------------------------------------
# CHARGEMENT DU DICTIONNAIRE (sert aux tools get_dictionnaire et au garde-fou)
# -----------------------------------------------------------------------------
with open(CHEMIN_DICO, encoding="utf-8") as f:
    DICO = json.load(f)

# -----------------------------------------------------------------------------
# CONNEXION DUCKDB + chargement des données au 1er lancement
# -----------------------------------------------------------------------------
def get_connexion():
    """Ouvre la base DuckDB. Charge les CSV si la base n'existe pas encore."""
    db_existe = CHEMIN_DB.exists()
    con = duckdb.connect(str(CHEMIN_DB))
    if not db_existe:
        # Premier lancement : on charge les 3 CSV en tables DuckDB
        con.execute(f"""
            CREATE TABLE faits AS SELECT * FROM read_csv_auto('{CHEMIN_FAITS}');
            CREATE TABLE prestations AS SELECT * FROM read_csv_auto('{CHEMIN_PRESTATIONS}');
            CREATE TABLE atc AS SELECT * FROM read_csv_auto('{CHEMIN_ATC}');
        """)
        print("Base DuckDB créée et données chargées.")
    return con

CON = get_connexion()

# -----------------------------------------------------------------------------
# SERVEUR MCP
# -----------------------------------------------------------------------------
mcp = FastMCP("DAMIA")

# -----------------------------------------------------------------------------
# OUTIL 1 : query_depenses — la requête paramétrée principale
# -----------------------------------------------------------------------------
@mcp.tool()
def query_depenses(
    mesure: str = "montant_rembourse",
    poste: str | None = None,
    annee: int | None = None,
    region: str | None = None,
    age: str | None = None,
    sexe: str | None = None,
) -> str:
    """
    Calcule une mesure (montant remboursé, dépense engagée, nombre d'actes)
    sur les données Open DAMIR, avec filtres optionnels.

    Args:
        mesure: 'montant_rembourse', 'depense_engagee' ou 'nombre_actes'.
        poste: macro-catégorie ou sous-catégorie (ex: 'Optique Médicale', 'Audioprothèse',
               'Soins Dentaires & Orthodontie'). Voir list_valeurs('poste').
        annee: année de soins (2022 à 2025).
        region: libellé de région (ex: 'Île-de-France'). Voir list_valeurs('region').
        age: tranche d'âge (ex: '0-19 ans'). Voir list_valeurs('age').
        sexe: 'Masculin' ou 'Féminin'.

    Returns:
        Le résultat chiffré, formaté.
    """
    # Vérif de la mesure (garde-fou : refuse une mesure inconnue)
    if mesure not in MESURES:
        return (f"Mesure '{mesure}' inconnue. Mesures disponibles : "
                f"{', '.join(MESURES.keys())}.")
    colonne = MESURES[mesure]

    # Construction de la requête paramétrée (jointure faits <-> prestations sur prs_nat)
    where = []
    params = []
    if annee is not None:
        where.append("f.soi_ann = ?")
        params.append(annee)
    if poste is not None:
        # on cherche le poste dans macro OU sous-catégorie corrigée
        where.append("(p.macro_categorie = ? OR p.sous_categorie_cor = ?)")
        params.extend([poste, poste])
    if region is not None:
        where.append("f.ben_res_reg_libelle = ?")  # adapte selon ta colonne (code ou libellé)
        params.append(region)
    if age is not None:
        where.append("f.age_ben_snds_libelle = ?")  # idem
        params.append(age)
    if sexe is not None:
        where.append("f.ben_sex_cod_libelle = ?")
        params.append(sexe)

    clause = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f"""
        SELECT SUM(f."{colonne}") AS resultat
        FROM faits f
        JOIN prestations p ON f.prs_nat = p.prs_nat
        {clause}
    """
    res = CON.execute(sql, params).fetchone()
    valeur = res[0] if res and res[0] is not None else 0

    # Formatage lisible
    label = DICO["mesures"].get(mesure, {}).get("label", mesure)
    if mesure == "nombre_actes":
        return f"{label} : {valeur:,.0f} actes".replace(",", " ")
    # montants en euros -> on affiche en Md€ si gros
    if abs(valeur) >= 1e9:
        return f"{label} : {valeur/1e9:.2f} Md€"
    if abs(valeur) >= 1e6:
        return f"{label} : {valeur/1e6:.2f} M€"
    return f"{label} : {valeur:,.2f} €".replace(",", " ")


# -----------------------------------------------------------------------------
# OUTIL 2 : compare_periods — comparaison entre deux années
# -----------------------------------------------------------------------------
@mcp.tool()
def compare_periods(
    mesure: str = "montant_rembourse",
    poste: str | None = None,
    annee1: int = 2022,
    annee2: int = 2024,
) -> str:
    """
    Compare une mesure entre deux années pour un poste donné.

    Args:
        mesure: 'montant_rembourse', 'depense_engagee' ou 'nombre_actes'.
        poste: poste de soin (optionnel).
        annee1: première année.
        annee2: seconde année.
    """
    if mesure not in MESURES:
        return f"Mesure '{mesure}' inconnue."
    colonne = MESURES[mesure]

    def calcul(an):
        where = ["f.soi_ann = ?"]
        params = [an]
        if poste is not None:
            where.append("(p.macro_categorie = ? OR p.sous_categorie_cor = ?)")
            params.extend([poste, poste])
        sql = f"""
            SELECT SUM(f."{colonne}") FROM faits f
            JOIN prestations p ON f.prs_nat = p.prs_nat
            WHERE {' AND '.join(where)}
        """
        r = CON.execute(sql, params).fetchone()
        return r[0] if r and r[0] is not None else 0

    v1, v2 = calcul(annee1), calcul(annee2)
    if v1 == 0:
        evol = "non calculable (base nulle)"
    else:
        evol = f"{((v2 - v1) / v1) * 100:+.1f}%"
    label = DICO["mesures"].get(mesure, {}).get("label", mesure)
    p = f" pour {poste}" if poste else ""
    return (f"{label}{p} : {v1/1e9:.2f} Md€ en {annee1} → "
            f"{v2/1e9:.2f} Md€ en {annee2} (évolution : {evol})")


# -----------------------------------------------------------------------------
# OUTIL 3 : get_dictionnaire — définitions (le filet anti-hallucination)
# -----------------------------------------------------------------------------
@mcp.tool()
def get_dictionnaire(terme: str) -> str:
    """
    Renvoie la définition d'un terme métier ou d'une colonne à partir du
    dictionnaire sémantique DAMIR (mesures, dimensions, paniers...).

    Args:
        terme: le terme à définir (ex: 'depense_engagee', 'taux_couverture',
               'panier', 'region', 'optique').
    """
    terme_l = terme.lower().strip()
    # Recherche dans mesures, dimensions, postes...
    for section in ("mesures", "dimensions", "postes"):
        for cle, contenu in DICO.get(section, {}).items():
            if terme_l in cle.lower() or terme_l in str(contenu.get("label", "")).lower():
                definition = contenu.get("definition") or contenu.get("note") or ""
                return f"{contenu.get('label', cle)} : {definition}"
    # Paniers santé
    if "panier" in terme_l:
        ps = DICO.get("paniers_sante", {})
        return f"Paniers santé : {ps.get('definition', '')} Valeurs : {', '.join(ps.get('valeurs', []))}"
    return (f"Terme '{terme}' non trouvé dans le dictionnaire. "
            f"Essaie : montant_rembourse, depense_engagee, taux_couverture, panier, region, age.")


# -----------------------------------------------------------------------------
# OUTIL 4 : list_valeurs — liste les valeurs possibles d'une dimension
# -----------------------------------------------------------------------------
@mcp.tool()
def list_valeurs(dimension: str) -> str:
    """
    Liste les valeurs disponibles pour une dimension (poste, region, age, sexe, annee).

    Args:
        dimension: 'poste', 'region', 'age', 'sexe' ou 'annee'.
    """
    dim = dimension.lower().strip()

    if dim == "poste":
        # postes = macro-catégories du dictionnaire
        macros = DICO.get("classification_postes", {}).get("macro_categories", {})
        return "Postes disponibles (macro-catégories) : " + " | ".join(macros.keys())

    if dim in ("region", "age", "sexe"):
        vals = DICO.get("dimensions", {}).get(dim, {}).get("valeurs_disponibles", {})
        if isinstance(vals, dict):
            return f"Valeurs pour {dim} : " + ", ".join(f"{v}" for v in vals.values())
        return f"Valeurs pour {dim} : {vals}"

    if dim in ("annee", "année", "annees"):
        return "Années disponibles : 2022, 2023, 2024, 2025"

    return f"Dimension '{dimension}' inconnue. Essaie : poste, region, age, sexe, annee."


# -----------------------------------------------------------------------------
# DÉMARRAGE
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    # Le serveur communique via stdio (entrée/sortie standard) — protocole MCP
    mcp.run()
