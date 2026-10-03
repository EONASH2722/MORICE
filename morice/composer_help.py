"""Shared, factual composer descriptions and generation policy."""
from dataclasses import dataclass

PRECISION_HELP = ("Precision\nUses lower-randomness sampling (temperature 0.1, top-p 0.85) "
                  "and asks the model to be exact and state uncertainty. "
                  "It does not guarantee correctness or add a separate verification pass.")
CONTROLS = {
    "files": ("Files", "Files\nAttach local images and research documents (Ctrl+O)."),
    "voice": ("Voice", "Live Action\nEnter or exit voice and optional camera interaction."),
    "model": ("Model", "Model\nChoose the local GGUF file or configured Ollama model."),
    "project": ("Project", "Project\nSwitch between ordinary chat and the selected project workspace."),
    "tools": ("Tools", "Tools\nOpen available actions and search commands (Ctrl+K)."),
}


@dataclass(frozen=True)
class Sampling:
    temperature: float
    top_p: float


def sampling_settings(precision, needs_precision=False):
    return Sampling(0.1, 0.85) if precision else Sampling(0.2 if needs_precision else 0.5, 0.9)
