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
    return bool(_arrow_chain(prompt)) or any(
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
        if not matched:
            return None
        title, diagram_type, labels, indexed_edges = matched
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
