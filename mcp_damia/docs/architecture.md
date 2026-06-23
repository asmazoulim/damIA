# Architecture MCP DAMIA

## Vue d'ensemble

```
+-------------------------------------------------------+
|  UTILISATEUR : question en langage naturel            |
|  "Montant rembourse optique en 2023 ?"                |
+----------------------------+--------------------------+
                             |
                             v
+-------------------------------------------------------+
|  CLIENT  (src/client_ollama.py)                       |
|  - envoie la question a Ollama                        |
|  - recoit le choix d'outil + parametres               |
|  - execute l'outil, renvoie le resultat au LLM        |
+----------------------------+--------------------------+
              |                          ^
              v                          | resultat
+---------------------------+            |
|  OLLAMA (qwen2.5:7b)      |            |
|  100% local, sur CPU      |            |
|  Choisit l'outil a appeler|            |
+---------------------------+            |
              |                          |
              v                          |
+-------------------------------------------------------+
|  OUTILS METIER (src/outils.py)                        |
|  query_depenses / get_dictionnaire / list_valeurs     |
|  -> requetes SQL parametrees (PAS de SQL libre)       |
+----------------------------+--------------------------+
                             |
              +--------------+--------------+
              v                             v
+----------------------------+  +------------------------+
|  DuckDB (data/damia.duckdb)|  |  Dictionnaire semantique|
|  faits / prestations / atc |  |  (config/*.json)        |
|  ~11,4 M lignes            |  |  garde-fou anti-hallu.  |
+----------------------------+  +------------------------+
```

## Principe cle
Le LLM fait le MINIMUM (router vers un outil + parametres).
Le code Python + DuckDB fait le travail FIABLE.
=> reduit le risque d'hallucination, adapte a un petit modele local.

## Souverainete
Tout tourne en local : aucune donnee ne sort du poste.
Pas de cloud, pas d'API externe. Argument fort pour VYV.
