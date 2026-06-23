"""
Benchmark de rapidite pour Qwen via Ollama.
Lance EXACTEMENT le meme script sur ton PC et sur Colab, puis compare les tokens/s.

Prerequis : Ollama doit tourner (serveur sur http://127.0.0.1:11434)
            et le modele doit etre telecharge (ollama pull qwen2.5).

Usage : python benchmark_qwen.py
"""

import requests

# ---- Parametres : GARDE-LES IDENTIQUES sur PC et sur Colab ----
# IMPORTANT : mets ici le nom EXACT affiche par "ollama list"
# (par ex. "qwen2.5:latest", "qwen2.5:7b", "qwen2.5:3b"...)
MODELE = "qwen2.5:7b"
URL = "http://127.0.0.1:11434/api/generate"

# Questions de test : remplace-les par de vraies questions type de ta demo Damir
PROMPTS = [
    "Explique en trois phrases ce qu'est l'assurance maladie.",
    "Quels sont les principaux postes de depenses de sante en France ?",
    "Resume en deux phrases le role d'un assistant IA dans l'analyse de donnees.",
]


def une_mesure(prompt):
    """Envoie un prompt et renvoie (nb_tokens, duree_en_secondes) ou leve une erreur lisible."""
    r = requests.post(URL, json={
        "model": MODELE,
        "prompt": prompt,
        "stream": False
    }, timeout=600)
    data = r.json()

    # Si Ollama renvoie une erreur, on l'affiche clairement au lieu de planter
    if "error" in data:
        raise RuntimeError(f"Ollama a renvoye une erreur : {data['error']}")
    if "eval_count" not in data:
        raise RuntimeError(f"Reponse inattendue d'Ollama : {data}")

    tokens = data["eval_count"]
    duree_s = data["eval_duration"] / 1e9   # nanosecondes -> secondes
    return tokens, duree_s


def main():
    # Verifie que le serveur repond
    try:
        requests.get("http://127.0.0.1:11434", timeout=5)
    except Exception:
        print("ERREUR : Ollama ne repond pas sur le port 11434.")
        print("Verifie que le serveur tourne et que le modele est telecharge.")
        return

    print(f"Modele teste : {MODELE}")
    print("-" * 50)

    try:
        # Tour de chauffe : la 1re requete charge le modele en memoire, on l'ignore
        print("Tour de chauffe (ignore dans les resultats)...")
        une_mesure("Bonjour")

        # Mesures reelles
        resultats = []
        for i, prompt in enumerate(PROMPTS, 1):
            tokens, duree = une_mesure(prompt)
            vitesse = tokens / duree
            resultats.append(vitesse)
            print(f"Question {i} : {tokens} tokens en {duree:.2f}s  ->  {vitesse:.1f} tokens/s")

        moyenne = sum(resultats) / len(resultats)
        print("-" * 50)
        print(f"VITESSE MOYENNE : {moyenne:.1f} tokens/seconde")
        print()
        print("Note ce chiffre, puis lance le MEME script sur l'autre machine et compare.")

    except RuntimeError as e:
        print()
        print(str(e))
        print()
        print("Piste : verifie le nom du modele avec 'ollama list' et reporte-le exactement")
        print("dans la variable MODELE en haut de ce script.")


if __name__ == "__main__":
    main()