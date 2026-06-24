"""
benchmark_backends.py — Compare la VITESSE des differents modeles/backends.

A placer a la RACINE du projet (a cote du dossier src/), et lancer :
    python benchmark_backends.py

Mesure, pour chaque configuration, la latence et une estimation des tokens/s
sur les memes questions. Instancie chaque backend directement (sans le cache
get_backend) pour pouvoir comparer plusieurs modeles dans une seule execution.

NOTE : la vitesse depend de la MACHINE.
  - Sur ton PC (sans gros GPU) : Ollama sera plus rapide que Transformers.
  - Sur Colab avec GPU T4 : Transformers devient competitif/rapide.
Lance ce script aux DEUX endroits pour comparer les environnements.
"""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.backends import OllamaBackend, TransformersBackend  # APIBackend dispo aussi

# --- Configurations a comparer : (libelle, fabrique) ---
# Commente/decommente selon ce que tu veux tester et ce qui est dispo sur la machine.
CONFIGS = [
    ("Ollama qwen2.5:7b",       lambda: OllamaBackend(modele="qwen2.5:7b")),
    # ("Ollama llama3.1:8b",    lambda: OllamaBackend(modele="llama3.1:8b")),
    ("Transformers Qwen2.5-7B", lambda: TransformersBackend(model_id="Qwen/Qwen2.5-7B-Instruct")),
    # ("Transformers 4bit",     lambda: TransformersBackend(model_id="Qwen/Qwen2.5-7B-Instruct", quantize_4bit=True)),
]

# Vraies questions type de ta demo (le modele doit choisir un outil ; ici on mesure
# la generation brute du backend, pas le passage MCP, pour isoler la vitesse modele)
PROMPTS = [
    "Quel est le taux de couverture de l'optique en 2023 ?",
    "Combien l'Assurance Maladie a-t-elle rembourse pour le dentaire en 2024 ?",
    "Compare les depenses de pharmacie entre 2022 et 2024.",
]


def estimer_tokens(texte):
    """Estimation commune a tous les backends (~0.75 mot par token)."""
    return max(1, int(len(texte.split()) / 0.75))


def bencher(libelle, fabrique):
    print(f"\n=== {libelle} ===")
    try:
        t0 = time.time()
        backend = fabrique()
        print(f"Chargement du modele : {time.time() - t0:.1f}s")

        backend.generer("Bonjour")  # tour de chauffe, ignore

        lats, vits = [], []
        for i, prompt in enumerate(PROMPTS, 1):
            t0 = time.time()
            rep = backend.generer(prompt)
            d = time.time() - t0
            tok = estimer_tokens(rep)
            lats.append(d); vits.append(tok / d)
            print(f"  Q{i} : {d:.2f}s  (~{tok/d:.1f} tokens/s)")
        return (libelle, sum(lats)/len(lats), sum(vits)/len(vits))
    except Exception as e:
        print(f"  ECHEC : {e}")
        return (libelle, None, None)


def main():
    res = [bencher(l, f) for l, f in CONFIGS]
    print("\n" + "=" * 54)
    print("RECAPITULATIF (vitesse = plus haut est mieux)")
    print("=" * 54)
    print(f"{'Configuration':<28}{'Latence':>10}{'Vitesse':>14}")
    print("-" * 54)
    for l, lat, vit in res:
        if lat is None:
            print(f"{l:<28}{'echec':>10}")
        else:
            print(f"{l:<28}{lat:>8.2f}s{vit:>10.1f} t/s")


if __name__ == "__main__":
    main()
