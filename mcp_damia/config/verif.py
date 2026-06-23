import duckdb

r = duckdb.sql("""
    SELECT soi_ann, COUNT(*) AS nb_lignes
    FROM read_csv_auto('data/fact_damir_2022_2025.csv')
    GROUP BY soi_ann
    ORDER BY soi_ann
""").fetchall()

total = 0
for annee, n in r:
    print(f"{annee} : {n:,} lignes")
    total += n
print(f"TOTAL : {total:,} lignes")