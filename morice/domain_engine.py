from __future__ import annotations

import math
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MoleculeAtom:
    atom_id: int
    element: str
    x: float
    y: float
    z: float
    formal_charge: int = 0


@dataclass(frozen=True)
class MoleculeBond:
    first: int
    second: int
    order: int = 1


@dataclass
class MoleculeArtifact:
    title: str
    formula: str
    geometry: str
    electron_geometry: str
    atoms: list[MoleculeAtom]
    bonds: list[MoleculeBond]
    central_atom: int
    central_lone_pairs: int
    reference_angles: list[float]
    coordinate_model: str
    instruction: dict
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DiagramNode:
    node_id: str
    label: str
    lane: str = ""


@dataclass(frozen=True)
class DiagramEdge:
    source: str
    target: str
    label: str = ""


@dataclass
class DiagramArtifact:
    title: str
    diagram_type: str
    nodes: list[DiagramNode]
    edges: list[DiagramEdge]
    instruction: dict
    notes: list[str] = field(default_factory=list)


ELEMENT_COLORS = {
    "H": "#f4f6fa",
    "B": "#f0a36b",
    "C": "#727985",
    "N": "#4f78ff",
    "O": "#ef4d5e",
    "F": "#62d27b",
    "P": "#f29f38",
    "S": "#f4d447",
    "Cl": "#47c96a",
    "Br": "#a74c35",
    "I": "#7d4fa3",
    "Xe": "#62c5cf",
}


def atom_color(element: str) -> str:
    return ELEMENT_COLORS.get(element, "#a9b3c8")


def _unit(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(sum(component * component for component in vector))
    return tuple(component / max(1e-12, length) for component in vector)


def _tetrahedral_vectors() -> list[tuple[float, float, float]]:
    return [
        _unit((1.0, 1.0, 1.0)),
        _unit((1.0, -1.0, -1.0)),
        _unit((-1.0, 1.0, -1.0)),
        _unit((-1.0, -1.0, 1.0)),
    ]


GEOMETRY_VECTORS: dict[str, list[tuple[float, float, float]]] = {
    "linear": [(-1.0, 0.0, 0.0), (1.0, 0.0, 0.0)],
    "bent": [
        (-math.sin(math.radians(52.25)), -math.cos(math.radians(52.25)), 0.0),
        (math.sin(math.radians(52.25)), -math.cos(math.radians(52.25)), 0.0),
    ],
    "trigonal planar": [
        (1.0, 0.0, 0.0),
        (-0.5, math.sqrt(3.0) / 2.0, 0.0),
        (-0.5, -math.sqrt(3.0) / 2.0, 0.0),
    ],
    "tetrahedral": _tetrahedral_vectors(),
    "trigonal pyramidal": [
        _unit((1.0, -0.55, -0.45)),
        _unit((-1.0, -0.55, -0.45)),
        _unit((0.0, 1.0, -0.45)),
    ],
    "trigonal bipyramidal": [
        (1.0, 0.0, 0.0),
        (-0.5, math.sqrt(3.0) / 2.0, 0.0),
        (-0.5, -math.sqrt(3.0) / 2.0, 0.0),
        (0.0, 0.0, 1.0),
        (0.0, 0.0, -1.0),
    ],
    "seesaw": [
        (1.0, 0.0, 0.0),
        (-0.5, math.sqrt(3.0) / 2.0, 0.0),
        (0.0, 0.0, 1.0),
        (0.0, 0.0, -1.0),
    ],
    "t-shaped": [
        (1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0),
        (0.0, 0.0, -1.0),
    ],
    "octahedral": [
        (1.0, 0.0, 0.0),
        (-1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, -1.0, 0.0),
        (0.0, 0.0, 1.0),
        (0.0, 0.0, -1.0),
    ],
    "square planar": [
        (1.0, 0.0, 0.0),
        (-1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, -1.0, 0.0),
    ],
    "square pyramidal": [
        (1.0, 0.0, 0.0),
        (-1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, -1.0, 0.0),
        (0.0, 0.0, 1.0),
    ],
}


def _bent_vectors(angle_degrees: float) -> list[tuple[float, float, float]]:
    half_angle = math.radians(angle_degrees / 2.0)
    return [
        (-math.sin(half_angle), -math.cos(half_angle), 0.0),
        (math.sin(half_angle), -math.cos(half_angle), 0.0),
    ]


def _trigonal_pyramidal_vectors(angle_degrees: float) -> list[tuple[float, float, float]]:
    """Return three unit vectors with the requested equal pairwise bond angle."""
    cosine = math.cos(math.radians(angle_degrees))
    axial_squared = max(0.0, min(1.0, (cosine + 0.5) / 1.5))
    axial = -math.sqrt(axial_squared)
    radial = math.sqrt(max(0.0, 1.0 - axial_squared))
    return [
        (
            radial * math.cos(math.tau * index / 3.0),
            radial * math.sin(math.tau * index / 3.0),
            axial,
        )
        for index in range(3)
    ]


def _distorted_axial_vectors(angle_degrees: float) -> list[tuple[float, float, float]]:
    """Return two unit vectors separated by the requested axial angle."""
    inward = math.radians(max(0.0, min(90.0, (180.0 - angle_degrees) / 2.0)))
    return [
        (math.sin(inward), 0.0, math.cos(inward)),
        (math.sin(inward), 0.0, -math.cos(inward)),
    ]


def _molecule_vectors(specification: dict) -> tuple[list[tuple[float, float, float]], str]:
    """Build coordinates from reference angles when the geometry permits it."""
    geometry = str(specification["geometry"])
    angles = [float(value) for value in specification.get("angles", [])]
    if geometry == "bent" and angles:
        return _bent_vectors(angles[0]), "reference-angle"
    if geometry == "trigonal pyramidal" and angles:
        return _trigonal_pyramidal_vectors(angles[0]), "reference-angle"
    if geometry == "t-shaped" and len(angles) >= 2:
        return [(1.0, 0.0, 0.0), *_distorted_axial_vectors(angles[-1])], "reference-angle"
    if geometry == "seesaw" and len(angles) >= 3:
        equatorial_angle = math.radians(angles[1])
        equatorial = [
            (1.0, 0.0, 0.0),
            (math.cos(equatorial_angle), math.sin(equatorial_angle), 0.0),
        ]
        return [*equatorial, *_distorted_axial_vectors(angles[-1])], "reference-angle"
    return list(GEOMETRY_VECTORS.get(geometry, [])), "idealized-vsepr"


# This table deliberately covers only structures whose topology and VSEPR model
# are known here. Unknown formulas fail closed instead of receiving an invented
# molecule.
MOLECULE_LIBRARY: dict[str, dict] = {
    "H2O": {
        "central": "O",
        "outer": ["H", "H"],
        "geometry": "bent",
        "electron_geometry": "tetrahedral",
        "lone_pairs": 2,
        "angles": [104.5],
        "bond_orders": [1, 1],
    },
    "NH3": {
        "central": "N",
        "outer": ["H", "H", "H"],
        "geometry": "trigonal pyramidal",
        "electron_geometry": "tetrahedral",
        "lone_pairs": 1,
        "angles": [107.0],
        "bond_orders": [1, 1, 1],
    },
    "CH4": {
        "central": "C",
        "outer": ["H", "H", "H", "H"],
        "geometry": "tetrahedral",
        "electron_geometry": "tetrahedral",
        "lone_pairs": 0,
        "angles": [109.47],
        "bond_orders": [1, 1, 1, 1],
    },
    "CO2": {
        "central": "C",
        "outer": ["O", "O"],
        "geometry": "linear",
        "electron_geometry": "linear",
        "lone_pairs": 0,
        "angles": [180.0],
        "bond_orders": [2, 2],
    },
    "BF3": {
        "central": "B",
        "outer": ["F", "F", "F"],
        "geometry": "trigonal planar",
        "electron_geometry": "trigonal planar",
        "lone_pairs": 0,
        "angles": [120.0],
        "bond_orders": [1, 1, 1],
    },
    "SO2": {
        "central": "S",
        "outer": ["O", "O"],
        "geometry": "bent",
        "electron_geometry": "trigonal planar",
        "lone_pairs": 1,
        "angles": [119.0],
        "bond_orders": [2, 1],
        "notes": ["SO2 has resonance; the displayed bond orders are one canonical form."],
    },
    "SO3": {
        "central": "S",
        "outer": ["O", "O", "O"],
        "geometry": "trigonal planar",
        "electron_geometry": "trigonal planar",
        "lone_pairs": 0,
        "angles": [120.0],
        "bond_orders": [2, 2, 2],
        "notes": ["The three S-O bonds are symmetry-equivalent in the resonance hybrid."],
    },
    "SF4": {
        "central": "S",
        "outer": ["F", "F", "F", "F"],
        "geometry": "seesaw",
        "electron_geometry": "trigonal bipyramidal",
        "lone_pairs": 1,
        "angles": [87.0, 102.0, 173.0],
        "bond_orders": [1, 1, 1, 1],
        "notes": ["The lone pair occupies an equatorial site and compresses the ideal VSEPR angles."],
    },
    "PCL5": {
        "central": "P",
        "outer": ["Cl", "Cl", "Cl", "Cl", "Cl"],
        "geometry": "trigonal bipyramidal",
        "electron_geometry": "trigonal bipyramidal",
        "lone_pairs": 0,
        "angles": [90.0, 120.0, 180.0],
        "bond_orders": [1, 1, 1, 1, 1],
    },
    "CLF3": {
        "central": "Cl",
        "outer": ["F", "F", "F"],
        "geometry": "t-shaped",
        "electron_geometry": "trigonal bipyramidal",
        "lone_pairs": 2,
        "angles": [87.5, 175.0],
        "bond_orders": [1, 1, 1],
    },
    "SF6": {
        "central": "S",
        "outer": ["F", "F", "F", "F", "F", "F"],
        "geometry": "octahedral",
        "electron_geometry": "octahedral",
        "lone_pairs": 0,
        "angles": [90.0, 180.0],
        "bond_orders": [1, 1, 1, 1, 1, 1],
    },
    "XEF4": {
        "central": "Xe",
        "outer": ["F", "F", "F", "F"],
        "geometry": "square planar",
        "electron_geometry": "octahedral",
        "lone_pairs": 2,
        "angles": [90.0, 180.0],
        "bond_orders": [1, 1, 1, 1],
    },
    "XEF2": {
        "central": "Xe",
        "outer": ["F", "F"],
        "geometry": "linear",
        "electron_geometry": "trigonal bipyramidal",
        "lone_pairs": 3,
        "angles": [180.0],
        "bond_orders": [1, 1],
    },
    "BRF5": {
        "central": "Br",
        "outer": ["F", "F", "F", "F", "F"],
        "geometry": "square pyramidal",
        "electron_geometry": "octahedral",
        "lone_pairs": 1,
        "angles": [84.8, 90.0, 180.0],
        "bond_orders": [1, 1, 1, 1, 1],
    },
    "NH4+": {
        "central": "N",
        "outer": ["H", "H", "H", "H"],
        "geometry": "tetrahedral",
        "electron_geometry": "tetrahedral",
        "lone_pairs": 0,
        "angles": [109.47],
        "bond_orders": [1, 1, 1, 1],
        "formal_charge": 1,
    },
}


def _formula_from_prompt(prompt: str) -> str:
    normalized = (
        (prompt or "")
        .replace("₂", "2")
        .replace("₃", "3")
        .replace("₄", "4")
        .replace("₅", "5")
        .replace("₆", "6")
        .replace("⁺", "+")
    )
    for key in sorted(MOLECULE_LIBRARY, key=len, reverse=True):
        if re.search(
            rf"(?<![A-Za-z0-9]){re.escape(key)}(?![A-Za-z0-9])",
            normalized,
            flags=re.IGNORECASE,
        ):
            return key
    return ""


def wants_molecule(prompt: str) -> bool:
    lowered = (prompt or "").lower()
    formula = _formula_from_prompt(prompt)
    chemical_language = any(
        marker in lowered
        for marker in {
            "atom",
            "bond angle",
            "chemistry",
            "electron geometry",
            "hybridization",
            "lewis",
            "lone pair",
            "molecular geometry",
            "molecule",
            "vsepr",
        }
    )
    visual_language = bool(
        re.search(r"\b(?:draw|model|render|show|visuali[sz]e|structure)\b", lowered)
    )
    return bool(formula and (chemical_language or visual_language))


def build_molecule_artifact(prompt: str):
    formula_key = _formula_from_prompt(prompt)
    specification = MOLECULE_LIBRARY.get(formula_key)
    if not specification:
        return None
    geometry = str(specification["geometry"])
    vectors, coordinate_model = _molecule_vectors(specification)
    outer = list(specification["outer"])
    if len(vectors) != len(outer):
        return None

    central_charge = int(specification.get("formal_charge", 0))
    atoms = [
        MoleculeAtom(
            atom_id=0,
            element=str(specification["central"]),
            x=0.0,
            y=0.0,
            z=0.0,
            formal_charge=central_charge,
        )
    ]
    bond_length = 1.0
    for index, (element, vector) in enumerate(zip(outer, vectors), start=1):
        atoms.append(
            MoleculeAtom(
                atom_id=index,
                element=element,
                x=vector[0] * bond_length,
                y=vector[1] * bond_length,
                z=vector[2] * bond_length,
            )
        )
    bonds = [
        MoleculeBond(0, index, int(order))
        for index, order in enumerate(specification["bond_orders"], start=1)
    ]
    display_formula = "PCl5" if formula_key == "PCL5" else (
        "ClF3" if formula_key == "CLF3" else (
            "XeF4" if formula_key == "XEF4" else (
                "XeF2" if formula_key == "XEF2" else (
                    "BrF5" if formula_key == "BRF5" else formula_key
                )
            )
        )
    )
    instruction = {
        "simulationType": "molecule",
        "equations": [],
        "parameters": {
            "formula": display_formula,
            "geometry": geometry,
            "electronGeometry": specification["electron_geometry"],
            "centralLonePairs": specification["lone_pairs"],
            "referenceAnglesDegrees": list(specification["angles"]),
            "coordinateModel": coordinate_model,
            "views": ["2d", "3d"],
            "deterministic": True,
            "source": "curated-vsepr-library",
        },
    }
    molecule = MoleculeArtifact(
        title=f"{display_formula} molecular structure",
        formula=display_formula,
        geometry=geometry,
        electron_geometry=str(specification["electron_geometry"]),
        atoms=atoms,
        bonds=bonds,
        central_atom=0,
        central_lone_pairs=int(specification["lone_pairs"]),
        reference_angles=[float(value) for value in specification["angles"]],
        coordinate_model=coordinate_model,
        instruction=instruction,
        notes=list(specification.get("notes", [])),
    )
    from .science_engine import ScienceArtifact

    return ScienceArtifact(
        "chemistry",
        molecule.title,
        instruction,
        chemistry=molecule,
    )


KNOWN_DIAGRAMS: tuple[tuple[tuple[str, ...], str, str, list[str], list[tuple[int, int, str]]], ...] = (
    (
        ("osi", "osi model"),
        "OSI seven-layer model",
        "stack",
        ["Application", "Presentation", "Session", "Transport", "Network", "Data Link", "Physical"],
        [(0, 1, ""), (1, 2, ""), (2, 3, ""), (3, 4, ""), (4, 5, ""), (5, 6, "")],
    ),
    (
        ("tcp handshake", "three-way handshake", "3 way handshake"),
        "TCP three-way handshake",
        "sequence",
        ["Client: SYN", "Server: SYN-ACK", "Client: ACK", "Connection established"],
        [(0, 1, ""), (1, 2, ""), (2, 3, "")],
    ),
    (
        ("dns lookup", "dns resolution"),
        "DNS resolution",
        "flow",
        ["Client", "Recursive resolver", "Root server", "TLD server", "Authoritative server", "IP response"],
        [(0, 1, "query"), (1, 2, "query"), (2, 3, "referral"), (3, 4, "referral"), (4, 5, "answer")],
    ),
    (
        ("compiler stages", "compiler pipeline"),
        "Compiler pipeline",
        "flow",
        ["Source", "Lexer", "Parser", "Semantic analysis", "IR", "Optimization", "Code generation"],
        [(0, 1, ""), (1, 2, ""), (2, 3, ""), (3, 4, ""), (4, 5, ""), (5, 6, "")],
    ),
    (
        ("process lifecycle", "process states"),
        "Operating-system process lifecycle",
        "state",
        ["New", "Ready", "Running", "Waiting", "Terminated"],
        [(0, 1, "admit"), (1, 2, "dispatch"), (2, 1, "preempt"), (2, 3, "wait"), (3, 1, "event"), (2, 4, "exit")],
    ),
    (
        ("tcp/ip", "tcp ip model"),
        "TCP/IP model",
        "stack",
        ["Application", "Transport", "Internet", "Network access"],
        [(0, 1, ""), (1, 2, ""), (2, 3, "")],
    ),
    (
        ("https flow", "tls handshake", "ssl handshake"),
        "TLS-secured HTTPS connection",
        "sequence",
        ["Client hello", "Server hello + certificate", "Key agreement", "Finished", "Encrypted HTTP"],
        [(0, 1, ""), (1, 2, "verify"), (2, 3, "derive keys"), (3, 4, "secure channel")],
    ),
    (
        ("packet routing", "network routing", "router path"),
        "Packet routing path",
        "flow",
        ["Source host", "Default gateway", "Edge router", "Transit network", "Destination router", "Destination host"],
        [(0, 1, "frame"), (1, 2, "route"), (2, 3, "forward"), (3, 4, "forward"), (4, 5, "deliver")],
    ),
    (
        ("firewall flow", "firewall packet"),
        "Firewall decision flow",
        "flow",
        ["Incoming packet", "Interface policy", "State table", "Rule evaluation", "Allow", "Deny + log"],
        [(0, 1, ""), (1, 2, ""), (2, 4, "established"), (2, 3, "new"), (3, 4, "match allow"), (3, 5, "match deny")],
    ),
    (
        ("load balancer", "load balancing"),
        "Load-balancer request flow",
        "flow",
        ["Client", "DNS / Anycast", "Load balancer", "Health check", "Backend A", "Backend B"],
        [(0, 1, ""), (1, 2, ""), (2, 3, "select healthy"), (3, 4, ""), (3, 5, "")],
    ),
    (
        ("virtual memory", "paging address translation", "page table"),
        "Virtual-memory address translation",
        "flow",
        ["Virtual address", "TLB lookup", "Page-table walk", "Physical frame", "Memory access", "Page fault handler"],
        [(0, 1, ""), (1, 3, "hit"), (1, 2, "miss"), (2, 3, "present"), (2, 5, "not present"), (3, 4, "")],
    ),
    (
        ("cpu scheduling", "process scheduling"),
        "CPU scheduling cycle",
        "state",
        ["Ready queue", "Dispatcher", "Running", "Waiting I/O", "Completed"],
        [(0, 1, "select"), (1, 2, "dispatch"), (2, 0, "preempt"), (2, 3, "block"), (3, 0, "wake"), (2, 4, "exit")],
    ),
    (
        ("deadlock", "resource allocation graph"),
        "Deadlock resource cycle",
        "state",
        ["Process A", "Resource 1", "Process B", "Resource 2"],
        [(0, 1, "requests"), (1, 2, "held by"), (2, 3, "requests"), (3, 0, "held by")],
    ),
    (
        ("er diagram", "entity relationship"),
        "Entity-relationship model",
        "flow",
        ["User", "Order", "Order item", "Product", "Payment"],
        [(0, 1, "places 1:N"), (1, 2, "contains 1:N"), (2, 3, "references N:1"), (1, 4, "paid by 1:1")],
    ),
    (
        ("sql join", "database join"),
        "SQL join pipeline",
        "flow",
        ["Left relation", "Join key", "Join algorithm", "Right relation", "Matched rows", "Result projection"],
        [(0, 1, ""), (3, 1, ""), (1, 2, ""), (2, 4, ""), (4, 5, "")],
    ),
    (
        ("database transaction", "acid transaction", "transaction lifecycle"),
        "ACID transaction lifecycle",
        "state",
        ["Begin", "Read / write", "Constraint checks", "Commit log", "Durable commit", "Rollback"],
        [(0, 1, ""), (1, 2, ""), (2, 3, "valid"), (3, 4, "flush"), (2, 5, "invalid"), (1, 5, "error")],
    ),
    (
        ("b+ tree", "b plus tree", "database index"),
        "B+ tree index",
        "tree",
        ["Root keys", "Internal page A", "Internal page B", "Leaf 1", "Leaf 2", "Leaf 3", "Leaf 4"],
        [(0, 1, ""), (0, 2, ""), (1, 3, ""), (1, 4, ""), (2, 5, ""), (2, 6, ""), (3, 4, "next"), (4, 5, "next"), (5, 6, "next")],
    ),
    (
        ("neural network", "feedforward network"),
        "Feed-forward neural network",
        "flow",
        ["Input features", "Hidden layer 1", "Activation", "Hidden layer 2", "Output probabilities"],
        [(0, 1, "weights"), (1, 2, ""), (2, 3, "weights"), (3, 4, "softmax")],
    ),
    (
        ("transformer architecture", "attention architecture"),
        "Transformer processing path",
        "flow",
        ["Tokens", "Embeddings + position", "Multi-head attention", "Add + norm", "Feed-forward", "Output logits"],
        [(0, 1, ""), (1, 2, "Q K V"), (2, 3, "residual"), (3, 4, ""), (4, 5, "")],
    ),
    (
        ("gradient descent", "optimization steps"),
        "Gradient-descent iteration",
        "flow",
        ["Parameters", "Forward pass", "Loss", "Gradient", "Optimizer update", "New parameters"],
        [(0, 1, ""), (1, 2, ""), (2, 3, "differentiate"), (3, 4, ""), (4, 5, ""), (5, 1, "next step")],
    ),
    (
        ("rsa", "rsa encryption"),
        "RSA operation flow",
        "flow",
        ["Choose primes p, q", "Compute n and phi(n)", "Choose public exponent e", "Derive private exponent d", "Encrypt with public key", "Decrypt with private key"],
        [(0, 1, ""), (1, 2, ""), (2, 3, ""), (2, 4, ""), (4, 5, "")],
    ),
    (
        ("aes", "aes encryption"),
        "AES round structure",
        "flow",
        ["Plaintext state", "AddRoundKey", "SubBytes", "ShiftRows", "MixColumns", "Next round / ciphertext"],
        [(0, 1, ""), (1, 2, ""), (2, 3, ""), (3, 4, ""), (4, 5, "")],
    ),
    (
        ("digital signature", "signature verification"),
        "Digital-signature verification",
        "flow",
        ["Message", "Hash function", "Private-key signature", "Public-key verification", "Recomputed hash", "Valid / invalid"],
        [(0, 1, ""), (1, 2, "sign"), (2, 3, ""), (0, 4, "hash"), (3, 5, "compare"), (4, 5, "compare")],
    ),
    (
        ("photosynthesis", "photosynthesis cycle"),
        "Photosynthesis overview",
        "flow",
        ["Light", "Water", "Light reactions", "ATP + NADPH", "Calvin cycle", "Glucose", "Oxygen"],
        [(0, 2, ""), (1, 2, ""), (2, 3, ""), (2, 6, "releases"), (3, 4, ""), (4, 5, "")],
    ),
    (
        ("protein synthesis", "transcription translation"),
        "Protein synthesis",
        "flow",
        ["DNA gene", "Transcription", "mRNA", "Ribosome", "tRNA + amino acids", "Polypeptide"],
        [(0, 1, ""), (1, 2, ""), (2, 3, ""), (4, 3, ""), (3, 5, "translation")],
    ),
    (
        ("cell cycle", "mitosis stages"),
        "Cell cycle",
        "state",
        ["G1 growth", "S DNA replication", "G2 preparation", "Mitosis", "Cytokinesis"],
        [(0, 1, ""), (1, 2, ""), (2, 3, ""), (3, 4, ""), (4, 0, "daughter cells")],
    ),
    (
        ("food chain", "food web"),
        "Food-chain energy flow",
        "flow",
        ["Sun", "Producer", "Primary consumer", "Secondary consumer", "Decomposer", "Nutrients"],
        [(0, 1, "energy"), (1, 2, ""), (2, 3, ""), (1, 4, "matter"), (2, 4, "matter"), (3, 4, "matter"), (4, 5, ""), (5, 1, "")],
    ),
    (
        ("logic gates", "digital logic"),
        "Digital logic path",
        "flow",
        ["Input A", "Input B", "AND / OR stage", "NOT stage", "Output Q"],
        [(0, 2, ""), (1, 2, ""), (2, 3, ""), (3, 4, "")],
    ),
    (
        ("software development lifecycle", "sdlc"),
        "Software development lifecycle",
        "flow",
        ["Requirements", "Design", "Implementation", "Testing", "Deployment", "Monitoring"],
        [(0, 1, ""), (1, 2, ""), (2, 3, ""), (3, 4, "pass"), (4, 5, ""), (5, 0, "feedback")],
    ),
    (
        ("rc circuit", "capacitor charging"),
        "RC charging circuit",
        "flow",
        ["Voltage source", "Switch", "Resistor R", "Capacitor C", "Return path", "Voltage measurement"],
        [(0, 1, ""), (1, 2, ""), (2, 3, "current i(t)"), (3, 4, ""), (4, 0, ""), (3, 5, "Vc(t)")],
    ),
    (
        ("rlc circuit", "resonant circuit"),
        "Series RLC circuit",
        "flow",
        ["AC source", "Resistor R", "Inductor L", "Capacitor C", "Return path", "Response measurement"],
        [(0, 1, ""), (1, 2, ""), (2, 3, ""), (3, 4, ""), (4, 0, ""), (3, 5, "Vout")],
    ),
    (
        ("kirchhoff", "kcl", "kvl"),
        "Kirchhoff circuit analysis",
        "flow",
        ["Source", "Node A", "Branch current I1", "Branch current I2", "Node B", "Return loop"],
        [(0, 1, ""), (1, 2, "I1"), (1, 3, "I2"), (2, 4, ""), (3, 4, ""), (4, 5, ""), (5, 0, "KVL loop")],
    ),
    (
        ("water cycle", "hydrologic cycle"),
        "Water cycle",
        "flow",
        ["Ocean and lakes", "Evaporation", "Condensation", "Clouds", "Precipitation", "Runoff and groundwater"],
        [(0, 1, "solar energy"), (1, 2, ""), (2, 3, ""), (3, 4, ""), (4, 5, ""), (5, 0, "")],
    ),
    (
        ("carbon cycle",),
        "Carbon cycle",
        "flow",
        ["Atmospheric CO2", "Photosynthesis", "Biomass", "Respiration", "Decomposition", "Ocean / geological storage", "Combustion"],
        [(0, 1, ""), (1, 2, ""), (2, 3, ""), (3, 0, ""), (2, 4, ""), (4, 0, ""), (4, 5, ""), (5, 6, ""), (6, 0, "")],
    ),
    (
        ("plate tectonics", "tectonic plates"),
        "Plate-boundary interactions",
        "flow",
        ["Mantle convection", "Divergent boundary", "New crust", "Convergent boundary", "Subduction / uplift", "Transform boundary", "Earthquakes"],
        [(0, 1, ""), (1, 2, ""), (0, 3, ""), (3, 4, ""), (0, 5, ""), (5, 6, "")],
    ),
    (
        ("volcano", "volcanic eruption"),
        "Volcanic system",
        "flow",
        ["Mantle melt", "Magma chamber", "Conduit", "Vent", "Lava and ash", "Cooling rock"],
        [(0, 1, ""), (1, 2, "pressure"), (2, 3, ""), (3, 4, "eruption"), (4, 5, "")],
    ),
    (
        ("earthquake", "seismic waves"),
        "Earthquake wave propagation",
        "flow",
        ["Fault stress", "Rupture at focus", "P waves", "S waves", "Surface waves", "Ground motion"],
        [(0, 1, "release"), (1, 2, ""), (1, 3, ""), (2, 4, "arrive first"), (3, 4, "arrive second"), (4, 5, "")],
    ),
    (
        ("supply and demand", "market equilibrium"),
        "Supply and demand relationships",
        "flow",
        ["Price", "Quantity demanded", "Quantity supplied", "Market comparison", "Shortage", "Equilibrium", "Surplus"],
        [(0, 1, "inverse relation"), (0, 2, "direct relation"), (1, 3, ""), (2, 3, ""), (3, 4, "Qd > Qs"), (3, 5, "Qd = Qs"), (3, 6, "Qs > Qd")],
    ),
    (
        ("compound interest", "interest compounding"),
        "Compound-interest accumulation",
        "flow",
        ["Principal P", "Periodic rate r/n", "Compounding period", "Updated balance", "Repeat n*t times", "Future value A"],
        [(0, 2, ""), (1, 2, ""), (2, 3, "multiply by 1+r/n"), (3, 4, ""), (4, 2, "next period"), (4, 5, "complete")],
    ),
    (
        ("solar system hierarchy", "planet system"),
        "Solar-system hierarchy",
        "tree",
        ["Sun", "Inner planets", "Outer planets", "Dwarf planets", "Asteroid belt", "Moons"],
        [(0, 1, "orbit"), (0, 2, "orbit"), (0, 3, "orbit"), (0, 4, "orbit"), (1, 5, "satellites"), (2, 5, "satellites")],
    ),
)


def _arrow_chain(prompt: str) -> list[str]:
    match = re.search(
        r"(?:flowchart|pipeline|diagram)\s*(?::|of)?\s*(.+)",
        prompt or "",
        flags=re.IGNORECASE,
    )
    if not match or not re.search(r"(?:->|→|=>)", match.group(1)):
        return []
    pieces = re.split(r"\s*(?:->|→|=>)\s*", match.group(1))
    labels = [re.sub(r"\s+", " ", piece).strip(" .;:,")[:72] for piece in pieces]
    return [label for label in labels if label][:12]


def _explicit_diagram_labels(prompt: str) -> list[str]:
    text = prompt or ""
    timeline = re.findall(
        r"\b((?:18|19|20|21)\d{2})\s*(?::|-)\s*([^,;\n]{2,56})",
        text,
    )
    if len(timeline) >= 2:
        return [f"{year}: {label.strip()}" for year, label in timeline[:12]]

    bullet_labels = re.findall(
        r"(?m)^\s*(?:[-*]|\d+[.)])\s+([^\n]{2,72})",
        text,
    )
    if len(bullet_labels) >= 2:
        return [re.sub(r"\s+", " ", label).strip(" .;:,") for label in bullet_labels[:12]]

    match = re.search(
        r"\b(?:class diagram|diagram|flowchart|gantt chart|mind map|pipeline|"
        r"sequence diagram|state diagram|timeline|uml)\b\s*(?:of|for)?\s*[:\-]\s*(.+)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return []
    labels = [
        re.sub(r"\s+", " ", item).strip(" .;:,")
        for item in re.split(r"[,;\n]+", match.group(1))
    ]
    return [label[:72] for label in labels if 2 <= len(label) <= 72][:12]


def wants_diagram(prompt: str) -> bool:
    lowered = (prompt or "").lower()
    visual = bool(
        re.search(
            r"\b(?:animate|diagram|draw|flowchart|model|show|timeline|tree|visuali[sz]e)\b",
            lowered,
        )
    )
    if not visual:
        return False
    return bool(_arrow_chain(prompt) or len(_explicit_diagram_labels(prompt)) >= 2) or any(
        any(marker in lowered for marker in aliases)
        for aliases, _title, _kind, _nodes, _edges in KNOWN_DIAGRAMS
    )


def build_diagram_artifact(prompt: str):
    chain = _arrow_chain(prompt)
    if chain:
        title = "Process flow"
        diagram_type = "flow"
        labels = chain
        indexed_edges = [(index, index + 1, "") for index in range(len(labels) - 1)]
    else:
        lowered = (prompt or "").lower()
        matched = next(
            (
                (title, diagram_type, labels, edges)
                for aliases, title, diagram_type, labels, edges in KNOWN_DIAGRAMS
                if any(marker in lowered for marker in aliases)
            ),
            None,
        )
        if matched:
            title, diagram_type, labels, indexed_edges = matched
        else:
            labels = _explicit_diagram_labels(prompt)
            if len(labels) < 2:
                return None
            if "timeline" in lowered:
                diagram_type = "timeline"
                title = "Timeline"
            elif "mind map" in lowered:
                diagram_type = "mind-map"
                title = "Mind map"
            elif "state diagram" in lowered:
                diagram_type = "state"
                title = "State diagram"
            elif "class diagram" in lowered or "uml" in lowered:
                diagram_type = "class"
                title = "UML class diagram"
            else:
                diagram_type = "flow"
                title = "Structured process diagram"
            if diagram_type == "mind-map":
                indexed_edges = [(0, index, "") for index in range(1, len(labels))]
            else:
                indexed_edges = [
                    (index, index + 1, "") for index in range(len(labels) - 1)
                ]
    nodes = [
        DiagramNode(str(index), label, "stack" if diagram_type == "stack" else "")
        for index, label in enumerate(labels)
    ]
    edges = [
        DiagramEdge(str(source), str(target), label)
        for source, target, label in indexed_edges
        if 0 <= source < len(nodes) and 0 <= target < len(nodes)
    ]
    instruction = {
        "simulationType": "diagram",
        "equations": [],
        "parameters": {
            "diagramType": diagram_type,
            "layout": "vertical" if diagram_type == "stack" else "horizontal",
            "deterministic": True,
        },
    }
    diagram = DiagramArtifact(title, diagram_type, nodes, edges, instruction)
    from .science_engine import ScienceArtifact

    return ScienceArtifact("diagram", title, instruction, diagram=diagram)
