from __future__ import annotations

import math
import re
from dataclasses import dataclass, field


@dataclass
class BiologyArtifact:
    title: str
    model_type: str
    labels: list[str]
    points: list[tuple[float, float, float]]
    connections: list[tuple[int, int, str]]
    instruction: dict
    notes: list[str] = field(default_factory=list)


@dataclass
class DataStructureArtifact:
    title: str
    structures: list[str]
    initial_values: list[int]
    instruction: dict


BIOLOGY_MARKERS = {
    "biology",
    "cell",
    "chromosome",
    "dna",
    "double helix",
    "genetics",
    "neuron",
    "organ",
    "protein",
    "rna",
}

DATA_STRUCTURE_MARKERS = {
    "avl tree",
    "binary search tree",
    "bst",
    "data structure",
    "hash table",
    "linked list",
    "queue",
    "stack",
}


def wants_biology(prompt: str) -> bool:
    lowered = (prompt or "").lower()
    visual = bool(
        re.search(r"\b(?:animate|draw|model|render|show|visuali[sz]e)\b", lowered)
    )
    return visual and any(marker in lowered for marker in BIOLOGY_MARKERS)


def build_biology_artifact(prompt: str):
    lowered = (prompt or "").lower()
    if "dna" in lowered or "double helix" in lowered or "chromosome" in lowered:
        labels = ["5' strand", "A-T", "C-G", "G-C", "T-A", "3' strand"]
        points: list[tuple[float, float, float]] = []
        connections: list[tuple[int, int, str]] = []
        turns = 14
        for index in range(turns):
            angle = index * 0.72
            z = (index - (turns - 1) / 2) * 0.32
            left = (0.9 * math.cos(angle), 0.9 * math.sin(angle), z)
            right = (-left[0], -left[1], z)
            points.extend((left, right))
            connections.append((index * 2, index * 2 + 1, "base pair"))
            if index:
                connections.extend(
                    (
                        ((index - 1) * 2, index * 2, "backbone"),
                        ((index - 1) * 2 + 1, index * 2 + 1, "backbone"),
                    )
                )
        model_type = "dna"
        title = "DNA double helix"
        notes = ["Complementary base-pair rungs", "Antiparallel sugar-phosphate backbones"]
    elif "neuron" in lowered:
        labels = ["Dendrites", "Cell body", "Nucleus", "Axon", "Myelin", "Terminals"]
        points = [
            (-1.7, 0.8, 0.0), (-0.5, 0.0, 0.0), (-0.5, 0.0, 0.2),
            (0.7, 0.0, 0.0), (1.5, 0.0, 0.0), (2.2, 0.35, 0.0),
        ]
        connections = [(0, 1, "input"), (1, 3, "signal"), (3, 4, "signal"), (4, 5, "output")]
        model_type = "neuron"
        title = "Neuron signal pathway"
        notes = ["Signal direction runs from dendrites through the axon to terminals"]
    else:
        labels = ["Cell membrane", "Cytoplasm", "Nucleus", "Mitochondrion", "Ribosome"]
        points = [
            (0.0, 0.0, 0.0), (0.25, -0.15, 0.0), (-0.2, 0.1, 0.2),
            (0.55, 0.25, -0.1), (-0.5, -0.35, 0.15),
        ]
        connections = [(0, index, "contains") for index in range(1, len(points))]
        model_type = "cell"
        title = "Eukaryotic cell"
        notes = ["Simplified educational model; organelles are not to scale"]
    instruction = {
        "simulationType": "biology",
        "equations": [],
        "parameters": {
            "modelType": model_type,
            "views": ["2d", "3d"],
            "animated": True,
            "deterministic": True,
        },
    }
    artifact = BiologyArtifact(
        title, model_type, labels, points, connections, instruction, notes
    )
    from .science_engine import ScienceArtifact

    return ScienceArtifact("biology", title, instruction, biology=artifact)


def wants_data_structures(prompt: str) -> bool:
    lowered = (prompt or "").lower()
    visual = bool(
        re.search(r"\b(?:animate|draw|render|show|visuali[sz]e)\b", lowered)
    )
    return visual and any(marker in lowered for marker in DATA_STRUCTURE_MARKERS)


def build_data_structure_artifact(prompt: str):
    lowered = (prompt or "").lower()
    requested: list[str] = []
    options = (
        ("Binary Search Tree", ("binary search tree", "bst")),
        ("AVL Tree", ("avl tree",)),
        ("Graph", ("graph",)),
        ("Linked List", ("linked list",)),
        ("Queue", ("queue",)),
        ("Stack", ("stack",)),
        ("Hash Table", ("hash table", "hash map")),
    )
    for label, aliases in options:
        if any(alias in lowered for alias in aliases):
            requested.append(label)
    if not requested or "every structure" in lowered or "all structure" in lowered:
        requested = [label for label, _aliases in options]
    instruction = {
        "simulationType": "data-structures",
        "equations": [],
        "parameters": {
            "structures": requested,
            "operations": ["insert", "delete", "search"],
            "animated": True,
            "complexityDisplay": True,
            "deterministic": True,
        },
    }
    artifact = DataStructureArtifact(
        "Interactive data-structure lab",
        requested,
        [40, 20, 60, 10, 30, 50, 70],
        instruction,
    )
    from .science_engine import ScienceArtifact

    return ScienceArtifact(
        "data-structures",
        artifact.title,
        instruction,
        data_structures=artifact,
    )
