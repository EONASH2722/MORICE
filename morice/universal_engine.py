from __future__ import annotations

import os
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ChartPoint:
    label: str
    x: float
    y: float


@dataclass
class ChartArtifact:
    title: str
    chart_type: str
    points: list[ChartPoint]
    instruction: dict
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ScenePrimitive:
    shape: str
    center: tuple[float, float, float]
    size: tuple[float, float, float]
    color: str
    label: str


@dataclass(frozen=True)
class SceneConnection:
    first: int
    second: int
    label: str = ""


@dataclass
class SceneArtifact:
    title: str
    scene_type: str
    primitives: list[ScenePrimitive]
    connections: list[SceneConnection]
    instruction: dict
    notes: list[str] = field(default_factory=list)


@dataclass
class DocumentArtifact:
    title: str
    path: str
    extension: str
    size_bytes: int
    instruction: dict


_CHART_WORDS = {
    "bar chart": "bar",
    "bar graph": "bar",
    "pie chart": "pie",
    "scatter plot": "scatter",
    "scatter chart": "scatter",
    "histogram": "histogram",
    "line chart": "line",
    "line graph": "line",
}

_SCENE_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("robot", ("robot", "humanoid robot")),
    ("drone", ("drone", "quadcopter")),
    ("vehicle", ("vehicle", "car", "automobile")),
    ("aircraft", ("aircraft", "airplane", "aeroplane", "plane")),
    ("ship", ("ship", "boat", "vessel")),
    ("building", ("building", "house", "skyscraper")),
    ("bridge", ("bridge",)),
    ("engine", ("engine", "motor")),
    ("cpu", ("cpu", "processor")),
    ("gpu", ("gpu", "graphics card")),
    ("motherboard", ("motherboard", "mainboard")),
    ("camera", ("camera",)),
    ("watch", ("watch", "wristwatch")),
)

DOCUMENT_EXTENSIONS = {
    ".bmp",
    ".csv",
    ".gif",
    ".jpeg",
    ".jpg",
    ".json",
    ".md",
    ".pdf",
    ".png",
    ".py",
    ".txt",
    ".webp",
    ".xml",
    ".yaml",
    ".yml",
}


def _visual_request(prompt: str) -> bool:
    return bool(
        re.search(
            r"\b(?:animate|chart|diagram|draw|model|render|show|visuali[sz]e)\b",
            (prompt or "").lower(),
        )
    )


def _contains_alias(text: str, alias: str) -> bool:
    return bool(
        re.search(
            rf"(?<![A-Za-z0-9_]){re.escape(alias)}(?![A-Za-z0-9_])",
            text,
            flags=re.IGNORECASE,
        )
    )


def _named_values(prompt: str) -> list[ChartPoint]:
    points: list[ChartPoint] = []
    pattern = re.compile(
        r"([A-Za-z][A-Za-z0-9 _-]{0,28}?)\s*(?::|=)\s*"
        r"(-?(?:\d+(?:\.\d*)?|\.\d+))"
    )
    for index, match in enumerate(pattern.finditer(prompt or "")):
        label = re.sub(r"\s+", " ", match.group(1)).strip(" ,;:-")
        label = re.sub(
            r"^.*?\b(?:chart|graph|plot)\b\s*(?:of\s+)?",
            "",
            label,
            flags=re.IGNORECASE,
        ).strip()
        if label:
            points.append(ChartPoint(label[-30:], float(index), float(match.group(2))))
    if len(points) >= 2:
        return points[:24]

    loose = re.compile(
        r"(?:^|[,;])\s*([A-Za-z][A-Za-z0-9 _-]{0,24}?)\s+"
        r"(-?(?:\d+(?:\.\d*)?|\.\d+))(?=\s*(?:[,;]|$))"
    )
    points = []
    for index, match in enumerate(loose.finditer(prompt or "")):
        points.append(
            ChartPoint(
                re.sub(r"\s+", " ", match.group(1)).strip()[-30:],
                float(index),
                float(match.group(2)),
            )
        )
    return points[:24]


def _coordinate_values(prompt: str) -> list[ChartPoint]:
    matches = re.findall(
        r"\(\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*,\s*"
        r"(-?(?:\d+(?:\.\d*)?|\.\d+))\s*\)",
        prompt or "",
    )
    return [
        ChartPoint(f"P{index + 1}", float(x_value), float(y_value))
        for index, (x_value, y_value) in enumerate(matches[:80])
    ]


def wants_chart(prompt: str) -> bool:
    lowered = (prompt or "").lower()
    if not _visual_request(prompt):
        return False
    chart_type = next(
        (value for marker, value in _CHART_WORDS.items() if marker in lowered),
        "",
    )
    if not chart_type:
        return False
    if chart_type in {"scatter", "line"} and len(_coordinate_values(prompt)) >= 2:
        return True
    return len(_named_values(prompt)) >= 2


def build_chart_artifact(prompt: str):
    lowered = (prompt or "").lower()
    chart_type = next(
        (value for marker, value in _CHART_WORDS.items() if marker in lowered),
        "",
    )
    if not chart_type:
        return None
    points = (
        _coordinate_values(prompt)
        if chart_type in {"scatter", "line"} and len(_coordinate_values(prompt)) >= 2
        else _named_values(prompt)
    )
    if len(points) < 2:
        return None
    title_match = re.search(
        r"(?:chart|graph|plot)\s+(?:of\s+)?([^.;\n]{3,72})",
        prompt or "",
        flags=re.IGNORECASE,
    )
    title = (
        re.sub(r"\s+", " ", title_match.group(1)).strip(" ,:-")
        if title_match
        else f"{chart_type.title()} chart"
    )
    instruction = {
        "simulationType": "chart",
        "equations": [],
        "parameters": {
            "chartType": chart_type,
            "interactive": True,
            "deterministic": True,
            "exports": ["png", "svg", "pdf"],
        },
    }
    chart = ChartArtifact(
        title=title[:80],
        chart_type=chart_type,
        points=points,
        instruction=instruction,
        notes=["Values are rendered directly from the numeric data in the prompt."],
    )
    from .science_engine import ScienceArtifact

    return ScienceArtifact("chart", chart.title, instruction, chart=chart)


def wants_scene(prompt: str) -> bool:
    lowered = (prompt or "").lower()
    if any(
        marker in lowered
        for marker in {
            "cpu scheduling",
            "process scheduling",
            "processor scheduling",
        }
    ):
        return False
    return _visual_request(prompt) and any(
        any(_contains_alias(lowered, alias) for alias in aliases)
        for _scene_type, aliases in _SCENE_ALIASES
    )


def _primitive(
    shape: str,
    center: tuple[float, float, float],
    size: tuple[float, float, float],
    color: str,
    label: str,
) -> ScenePrimitive:
    return ScenePrimitive(shape, center, size, color, label)


def _scene_parts(scene_type: str) -> tuple[list[ScenePrimitive], list[SceneConnection]]:
    blue = "#4aa8ff"
    green = "#63d5ad"
    gold = "#f1c75b"
    red = "#ef6d78"
    purple = "#a985ff"
    gray = "#9aa8ba"
    parts: dict[str, list[ScenePrimitive]] = {
        "robot": [
            _primitive("box", (0, 1.55, 0), (0.8, 0.65, 0.65), blue, "Head"),
            _primitive("box", (0, 0.55, 0), (1.15, 1.15, 0.62), purple, "Torso"),
            _primitive("box", (-0.9, 0.55, 0), (0.35, 1.15, 0.35), gray, "Left arm"),
            _primitive("box", (0.9, 0.55, 0), (0.35, 1.15, 0.35), gray, "Right arm"),
            _primitive("box", (-0.34, -0.75, 0), (0.4, 1.25, 0.45), blue, "Left leg"),
            _primitive("box", (0.34, -0.75, 0), (0.4, 1.25, 0.45), blue, "Right leg"),
        ],
        "drone": [
            _primitive("box", (0, 0, 0), (1.0, 0.28, 0.7), purple, "Flight controller"),
            _primitive("sphere", (-1.25, 0.75, 0), (0.38, 0.18, 0.38), blue, "Motor 1"),
            _primitive("sphere", (1.25, 0.75, 0), (0.38, 0.18, 0.38), blue, "Motor 2"),
            _primitive("sphere", (-1.25, -0.75, 0), (0.38, 0.18, 0.38), green, "Motor 3"),
            _primitive("sphere", (1.25, -0.75, 0), (0.38, 0.18, 0.38), green, "Motor 4"),
        ],
        "vehicle": [
            _primitive("box", (0, 0, 0), (2.8, 0.65, 1.15), blue, "Body"),
            _primitive("box", (0.2, 0.62, 0), (1.35, 0.65, 1.0), purple, "Cabin"),
            _primitive("cylinder", (-0.9, -0.45, -0.65), (0.52, 0.52, 0.22), gray, "Wheel"),
            _primitive("cylinder", (0.9, -0.45, -0.65), (0.52, 0.52, 0.22), gray, "Wheel"),
            _primitive("cylinder", (-0.9, -0.45, 0.65), (0.52, 0.52, 0.22), gray, "Wheel"),
            _primitive("cylinder", (0.9, -0.45, 0.65), (0.52, 0.52, 0.22), gray, "Wheel"),
        ],
        "aircraft": [
            _primitive("cylinder", (0, 0, 0), (3.4, 0.48, 0.48), blue, "Fuselage"),
            _primitive("box", (0, 0, 0), (1.0, 0.12, 3.8), purple, "Main wings"),
            _primitive("box", (-1.35, 0.22, 0), (0.6, 0.1, 1.55), green, "Tailplane"),
            _primitive("box", (-1.45, 0.5, 0), (0.42, 0.75, 0.1), red, "Vertical stabilizer"),
        ],
        "ship": [
            _primitive("box", (0, 0, 0), (3.2, 0.55, 1.25), blue, "Hull"),
            _primitive("box", (0.25, 0.58, 0), (1.35, 0.65, 0.9), gray, "Superstructure"),
            _primitive("cylinder", (-0.35, 1.08, 0), (0.25, 0.7, 0.25), red, "Stack"),
        ],
        "building": [
            _primitive("box", (0, 0, 0), (2.0, 3.2, 1.8), blue, "Structure"),
            _primitive("box", (0, -1.35, -0.92), (0.55, 0.8, 0.08), gold, "Entrance"),
            _primitive("box", (0, 1.75, 0), (2.2, 0.2, 2.0), purple, "Roof"),
        ],
        "bridge": [
            _primitive("box", (0, 0, 0), (4.2, 0.25, 0.9), blue, "Deck"),
            _primitive("box", (-1.4, -0.8, 0), (0.3, 1.7, 0.6), gray, "Pier 1"),
            _primitive("box", (1.4, -0.8, 0), (0.3, 1.7, 0.6), gray, "Pier 2"),
            _primitive("box", (-1.4, 1.0, 0), (0.25, 1.8, 0.35), purple, "Tower 1"),
            _primitive("box", (1.4, 1.0, 0), (0.25, 1.8, 0.35), purple, "Tower 2"),
        ],
        "engine": [
            _primitive("box", (0, 0, 0), (2.2, 1.35, 1.45), gray, "Engine block"),
            _primitive("cylinder", (-0.65, 0.75, 0), (0.48, 0.9, 0.48), red, "Cylinder 1"),
            _primitive("cylinder", (0, 0.75, 0), (0.48, 0.9, 0.48), gold, "Cylinder 2"),
            _primitive("cylinder", (0.65, 0.75, 0), (0.48, 0.9, 0.48), red, "Cylinder 3"),
            _primitive("cylinder", (0, -0.75, 0), (1.2, 0.35, 0.35), purple, "Crankshaft"),
        ],
        "cpu": [
            _primitive("box", (0, 0, 0), (2.5, 0.18, 2.5), green, "Package substrate"),
            _primitive("box", (0, 0.18, 0), (1.5, 0.24, 1.5), gray, "Heat spreader"),
            _primitive("box", (0, 0.34, 0), (0.9, 0.08, 0.9), blue, "Silicon die"),
        ],
        "gpu": [
            _primitive("box", (0, 0, 0), (3.4, 0.16, 1.6), green, "PCB"),
            _primitive("box", (-0.45, 0.2, 0), (1.1, 0.24, 1.1), purple, "GPU die"),
            _primitive("cylinder", (0.85, 0.32, 0), (0.85, 0.18, 0.85), gray, "Cooling fan"),
        ],
        "motherboard": [
            _primitive("box", (0, 0, 0), (3.4, 0.12, 2.8), green, "PCB"),
            _primitive("box", (-0.7, 0.18, 0.35), (0.9, 0.22, 0.9), purple, "CPU socket"),
            _primitive("box", (0.65, 0.18, 0.55), (1.2, 0.16, 0.22), blue, "Memory slots"),
            _primitive("box", (0.45, 0.18, -0.65), (1.8, 0.16, 0.25), gold, "PCIe slot"),
            _primitive("box", (-1.35, 0.3, 0.75), (0.35, 0.45, 0.85), gray, "Rear I/O"),
        ],
        "camera": [
            _primitive("box", (0, 0, 0), (2.3, 1.5, 0.9), blue, "Camera body"),
            _primitive("cylinder", (0, 0, 0.8), (1.0, 1.0, 1.2), gray, "Lens"),
            _primitive("box", (-0.65, 0.95, 0), (0.55, 0.35, 0.55), purple, "Viewfinder"),
        ],
        "watch": [
            _primitive("cylinder", (0, 0, 0), (1.45, 0.32, 1.45), blue, "Watch case"),
            _primitive("box", (0, 1.35, 0), (0.72, 1.4, 0.18), gray, "Upper strap"),
            _primitive("box", (0, -1.35, 0), (0.72, 1.4, 0.18), gray, "Lower strap"),
        ],
    }
    primitives = parts[scene_type]
    connections: list[SceneConnection] = []
    if scene_type == "drone":
        connections = [SceneConnection(0, index, "arm") for index in range(1, 5)]
    elif scene_type == "robot":
        connections = [SceneConnection(1, index, "joint") for index in (0, 2, 3, 4, 5)]
    return primitives, connections


def build_scene_artifact(prompt: str):
    lowered = (prompt or "").lower()
    scene_type = next(
        (
            key
            for key, aliases in _SCENE_ALIASES
            if any(_contains_alias(lowered, alias) for alias in aliases)
        ),
        "",
    )
    if not scene_type:
        return None
    primitives, connections = _scene_parts(scene_type)
    title = f"{scene_type.title()} schematic"
    instruction = {
        "simulationType": "scene",
        "equations": [],
        "parameters": {
            "sceneType": scene_type,
            "views": ["2d", "3d"],
            "interactive": True,
            "deterministic": True,
            "representation": "labeled-component-schematic",
        },
    }
    scene = SceneArtifact(
        title,
        scene_type,
        primitives,
        connections,
        instruction,
        [
            "This is a labeled component schematic, not a manufacturing CAD model.",
            "Relative placement is educational and is not dimensionally certified.",
        ],
    )
    from .science_engine import ScienceArtifact

    return ScienceArtifact("scene", title, instruction, scene=scene)


def _document_path(prompt: str) -> str:
    text = str(prompt or "")
    extension_pattern = "|".join(
        re.escape(extension.lstrip("."))
        for extension in sorted(DOCUMENT_EXTENSIONS, key=len, reverse=True)
    )
    quoted = re.search(
        rf"""["']([A-Za-z]:[\\/][^"']+?\.(?:{extension_pattern}))["']""",
        text,
        flags=re.IGNORECASE,
    )
    if quoted:
        return os.path.abspath(os.path.expanduser(quoted.group(1)))
    unquoted = re.search(
        rf"""([A-Za-z]:[\\/][^\r\n]+?\.(?:{extension_pattern}))(?=\s*$|[.;,])""",
        text,
        flags=re.IGNORECASE,
    )
    return (
        os.path.abspath(os.path.expanduser(unquoted.group(1).strip()))
        if unquoted
        else ""
    )


def wants_document(prompt: str) -> bool:
    lowered = (prompt or "").lower()
    visual = bool(
        re.search(
            r"\b(?:display|open|preview|render|show|view)\b",
            lowered,
        )
    )
    return visual and bool(_document_path(prompt))


def build_document_artifact(prompt: str):
    path = _document_path(prompt)
    if not path or not os.path.isfile(path):
        return None
    extension = os.path.splitext(path)[1].lower()
    if extension not in DOCUMENT_EXTENSIONS:
        return None
    instruction = {
        "simulationType": "document",
        "equations": [],
        "parameters": {
            "path": path,
            "extension": extension,
            "interactive": True,
            "deterministic": True,
        },
    }
    document = DocumentArtifact(
        title=os.path.basename(path),
        path=path,
        extension=extension,
        size_bytes=os.path.getsize(path),
        instruction=instruction,
    )
    from .science_engine import ScienceArtifact

    return ScienceArtifact("document", document.title, instruction, document=document)
