"""
src/backends.py — Couche d'abstraction multi-modeles pour DAMIA / MCP.

Le reste du projet n'appelle QUE backend.generer(prompt). Il ne sait pas s'il parle
a Ollama, a un modele Transformers (PyTorch), ou a une API. On change de moteur via
la variable d'environnement DAMIA_BACKEND, sans toucher au code metier :
    "ollama"        -> Ollama local        (DEFAUT, recommande sur ton PC)
    "transformers"  -> modele HuggingFace en PyTorch (recommande sur Colab GPU)
    "api"           -> API distante        (necessite DAMIA_API_KEY)

Le modele peut etre impose via DAMIA_MODELE (sinon valeur par defaut du backend).
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
# 2) Backend Ollama — defaut, aligne sur config.py
# ---------------------------------------------------------------
class OllamaBackend(ModelBackend):
    def __init__(self, modele=None, temperature=None):
        try:
            from config.config import MODELE_OLLAMA, TEMPERATURE
            defaut_modele, defaut_temp = MODELE_OLLAMA, TEMPERATURE
        except Exception:
            defaut_modele, defaut_temp = "qwen2.5:7b", 0.1
        self.modele = modele or os.environ.get("DAMIA_MODELE", defaut_modele)
        self.temperature = temperature if temperature is not None else defaut_temp

    def generer(self, prompt: str) -> str:
        import ollama
        rep = ollama.chat(
            model=self.modele,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": self.temperature},
        )
        return rep["message"]["content"]


# ---------------------------------------------------------------
# 3) Backend Transformers / PyTorch (HuggingFace)
#    - quantification 4 bits PAR DEFAUT si GPU present (= mollo sur la VRAM)
#    - tout force sur le GPU : pas d'offload CPU silencieux (= pas de lenteur mystere)
#    - si pas de GPU : avertissement clair (sur PC, prefere Ollama)
#    - dtype (et non torch_dtype, deprecie) ; max_new_tokens court (appels JSON brefs)
# ---------------------------------------------------------------
class TransformersBackend(ModelBackend):
    # Modele leger par defaut, adapte au tool-calling et au T4
    MODELE_DEFAUT = "Qwen/Qwen3-4B-Instruct-2507"

    def __init__(self, model_id=None, quantize_4bit=None, max_new_tokens=256):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.model_id = model_id or os.environ.get("DAMIA_MODELE", self.MODELE_DEFAUT)
        self.max_new_tokens = max_new_tokens
        gpu = torch.cuda.is_available()

        # Quantifier par defaut UNIQUEMENT si GPU (bitsandbytes exige CUDA)
        if quantize_4bit is None:
            quantize_4bit = gpu

        if not gpu:
            print("[TransformersBackend] ATTENTION : aucun GPU CUDA detecte. "
                  "Le modele tournera sur CPU (tres lent). Sur ce poste, "
                  "prefere Ollama : DAMIA_BACKEND=ollama.")

        self.tokenizer = AutoTokenizer.from_pretrained(self.model_id)

        kwargs = {}
        if gpu:
            # device_map fige : TOUT sur le GPU 0. Si ca deborde -> OOM CLAIR,
            # plutot qu'un offload CPU silencieux qui ruine la vitesse.
            kwargs["device_map"] = {"": 0}
            if quantize_4bit:
                from transformers import BitsAndBytesConfig
                kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.float16,
                )
            else:
                kwargs["dtype"] = torch.float16
        else:
            kwargs["dtype"] = torch.float32

        self.model = AutoModelForCausalLM.from_pretrained(self.model_id, **kwargs)

        dev = next(self.model.parameters()).device
        print(f"[TransformersBackend] {self.model_id} charge sur {dev} "
              f"(quantize_4bit={bool(quantize_4bit and gpu)}, "
              f"max_new_tokens={self.max_new_tokens})")

    def generer(self, prompt: str) -> str:
        messages = [{"role": "user", "content": prompt}]
        try:
            text = self.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        except Exception:
            text = prompt
        inputs = self.tokenizer(text, return_tensors="pt").to(self.model.device)
        # Greedy (do_sample=False) : sortie deterministe, ideal pour du JSON d'outil
        out = self.model.generate(**inputs, max_new_tokens=self.max_new_tokens,
                                  do_sample=False)
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
# 5) Fabrique (avec cache : un seul backend charge par processus)
# ---------------------------------------------------------------
_BACKEND = None
def get_backend(force_reload=False) -> ModelBackend:
    global _BACKEND
    if _BACKEND is not None and not force_reload:
        return _BACKEND
    choix = os.environ.get("DAMIA_BACKEND", "ollama").lower()
    if choix == "ollama":
        _BACKEND = OllamaBackend()
    elif choix == "transformers":
        _BACKEND = TransformersBackend()
    elif choix == "api":
        _BACKEND = APIBackend()
    else:
        raise ValueError(f"Backend inconnu : {choix}")
    return _BACKEND


if __name__ == "__main__":
    backend = get_backend()
    print(f"Backend actif : {backend.__class__.__name__}")
    print(backend.generer("Dis bonjour en une phrase."))