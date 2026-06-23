import duckdb
from config.config import CHEMIN_DB

con = duckdb.connect(str(CHEMIN_DB), read_only=True)

# Optique 2023
r = con.execute("""
SELECT SUM(f.mt_rembourse), SUM(f.total_actes_qte)
FROM faits f JOIN prestations p
  ON CAST(f.prs_nat AS VARCHAR)=CAST(p.prs_nat AS VARCHAR)
WHERE f.soi_ann=2023 AND p.sous_categorie_cor='Optique Médicale'
""").fetchone()
print(f"Optique 2023 : {r[0]/1e6:.1f} M€  |  {r[0]:,.0f} €  |  {r[1]:,.0f} actes")

# Total 2023
r2 = con.execute("SELECT SUM(mt_rembourse) FROM faits WHERE soi_ann=2023").fetchone()
print(f"Total 2023 : {r2[0]/1e9:.2f} Md€")

# Dentaire 2023
r3 = con.execute("""
SELECT SUM(f.mt_rembourse)
FROM faits f JOIN prestations p
  ON CAST(f.prs_nat AS VARCHAR)=CAST(p.prs_nat AS VARCHAR)
WHERE f.soi_ann=2023 AND p.macro_categorie='Soins Dentaires & Orthodontie'
""").fetchone()
print(f"Dentaire 2023 : {r3[0]/1e9:.2f} Md€")
con.close()