"""
Couche d'abstraction multi-modeles pour Damir / MCP.

Principe : le reste du projet n'appelle QUE backend.generer(prompt).
Il ne sait pas s'il parle a Ollama, a un modele Transformers local, ou a une API.
Pour changer de modele, on change la config (variable d'env) -- pas le code metier.

CORRECTION : l'OllamaBackend est desormais aligne avec config.py
(meme modele MODELE_OLLAMA, meme librairie `ollama` que ollama_client.py)
au lieu d'une 2e source de verite (DAMIA_MODELE + appel REST brut).

Choix du backend via la variable d'environnement DAMIA_BACKEND :
    "ollama"        -> Ollama local (defaut)
    "transformers"  -> modele Hugging Face charge en local (PyTorch)
    "api"           -> API distante (necessite DAMIA_API_KEY)
"""
import os
import sys
from pathlib import Path
from abc import ABC, abstractmethod
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------
# 1) Interface commune
# ---------------------------------------------------------------
class ModelBackend(ABC):
    @abstractmethod
    def generer(self, prompt: str) -> str:
        """Prend un prompt, renvoie le texte genere."""
        ...


# ---------------------------------------------------------------
# 2) Backend Ollama — aligne sur config.py et la lib `ollama`
# ---------------------------------------------------------------
class OllamaBackend(ModelBackend):
    def __init__(self, modele=None, temperature=None):
        # Source unique de verite : config.py (avec repli sur variable d'env)
        try:
            from config.config import MODELE_OLLAMA, TEMPERATURE
            defaut_modele, defaut_temp = MODELE_OLLAMA, TEMPERATURE
        except Exception:
            defaut_modele, defaut_temp = "qwen2.5:7b", 0.1
        self.modele = modele or os.environ.get("DAMIA_MODELE", defaut_modele)
        self.temperature = temperature if temperature is not None else defaut_temp

    def generer(self, prompt: str) -> str:
        import ollama  # meme librairie que ollama_client.py
        rep = ollama.chat(
            model=self.modele,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": self.temperature},
        )
        return rep["message"]["content"]


# ---------------------------------------------------------------
# 3) Backend Transformers / PyTorch (Hugging Face en local)
# ---------------------------------------------------------------
class TransformersBackend(ModelBackend):
    def __init__(self, model_id=None, quantize_4bit=False):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.model_id = model_id or os.environ.get(
            "DAMIA_MODELE", "Qwen/Qwen2.5-7B-Instruct"
        )
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_id)

        kwargs = {"device_map": "auto", "torch_dtype": torch.float16}
        if quantize_4bit:
            from transformers import BitsAndBytesConfig
            kwargs["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True)
            kwargs.pop("torch_dtype")

        self.model = AutoModelForCausalLM.from_pretrained(self.model_id, **kwargs)

    def generer(self, prompt: str) -> str:
        messages = [{"role": "user", "content": prompt}]
        try:
            text = self.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        except Exception:
            text = prompt
        inputs = self.tokenizer(text, return_tensors="pt").to(self.model.device)
        out = self.model.generate(**inputs, max_new_tokens=512)
        nouveaux = out[0][inputs["input_ids"].shape[1]:]
        return self.tokenizer.decode(nouveaux, skip_special_tokens=True)


# ---------------------------------------------------------------
# 4) Backend API distante
# ---------------------------------------------------------------
class APIBackend(ModelBackend):
    def __init__(self, modele=None):
        self.modele = modele or os.environ.get("DAMIA_MODELE", "claude-sonnet-4-6")
        self.cle = os.environ.get("DAMIA_API_KEY")
        if not self.cle:
            raise RuntimeError("Cle API manquante : definis DAMIA_API_KEY")

    def generer(self, prompt: str) -> str:
        import anthropic
        client = anthropic.Anthropic(api_key=self.cle)
        msg = client.messages.create(
            model=self.modele,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text


# ---------------------------------------------------------------
# 5) Fabrique
# ---------------------------------------------------------------
def get_backend() -> ModelBackend:
    choix = os.environ.get("DAMIA_BACKEND", "ollama").lower()
    if choix == "ollama":
        return OllamaBackend()
    elif choix == "transformers":
        return TransformersBackend()
    elif choix == "api":
        return APIBackend()
    else:
        raise ValueError(f"Backend inconnu : {choix}")


if __name__ == "__main__":
    backend = get_backend()
    print(f"Backend actif : {backend.__class__.__name__}")
    print(backend.generer("Dis bonjour en une phrase."))