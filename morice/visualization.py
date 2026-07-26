from __future__ import annotations

import copy
import hashlib
import os
import platform
import re
import threading
import time
import uuid
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Protocol

from .science_engine import (
    ScienceArtifact,
    build_graph_artifact,
    build_physics_artifact,
    wants_graph,
    wants_physics,
)
from .domain_engine import (
    build_diagram_artifact,
    build_molecule_artifact,
    wants_diagram,
    wants_molecule,
)
from .educational_engine import (
    build_biology_artifact,
    build_data_structure_artifact,
    wants_biology,
    wants_data_structures,
)


ProgressCallback = Callable[[str, str, int], None]


@dataclass(frozen=True)
class RendererCapability:
    renderer_id: str
    label: str
    available: bool
    interactive: bool
    backend: str
    reason: str = ""


@dataclass(frozen=True)
class VisualizationDecision:
    renderer_id: str
    reason: str
    confidence: float
    explicitly_requested: bool = True


@dataclass(frozen=True)
class VisualizationRequest:
    job_id: str
    prompt: str
    decision: VisualizationDecision
    created_at: float = field(default_factory=time.monotonic)


@dataclass
class VisualizationResult:
    job_id: str
    status: str
    renderer_id: str
    artifact: ScienceArtifact | None = None
    error: str = ""
    duration_ms: float = 0.0
    validated: bool = False
    from_cache: bool = False
    stages: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "ready" and self.validated and self.artifact is not None


class RendererPlugin(Protocol):
    renderer_id: str
    label: str
    interactive: bool

    def can_render(self, prompt: str) -> bool: ...

    def render(self, prompt: str) -> ScienceArtifact | None: ...

    def validate(self, artifact: ScienceArtifact) -> tuple[bool, str]: ...

    def estimate_bytes(self, artifact: ScienceArtifact) -> int: ...


class GraphRendererPlugin:
    renderer_id = "math.graph"
    label = "Interactive graph and surface"
    interactive = True

    def can_render(self, prompt: str) -> bool:
        return wants_graph(prompt)

    def render(self, prompt: str) -> ScienceArtifact | None:
        return build_graph_artifact(prompt)

    def validate(self, artifact: ScienceArtifact) -> tuple[bool, str]:
        graph = artifact.graph
        if artifact.kind != "graph" or graph is None:
            return False, "The graph engine did not return a graph artifact."
        if graph.surface is not None:
            surface = graph.surface
            if len(surface.x) < 2 or len(surface.y) < 2:
                return False, "The surface grid is too small to render."
            if len(surface.z) != len(surface.y):
                return False, "The surface row count does not match its y-axis."
            finite_count = 0
            for row in surface.z:
                if len(row) != len(surface.x):
                    return False, "A surface row does not match its x-axis."
                finite_count += sum(1 for value in row if _is_finite_number(value))
            if finite_count < 4:
                return False, "The surface contains no finite renderable region."
            return True, ""
        if not graph.series:
            return False, "The graph contains no drawable series."
        for series in graph.series:
            if len(series.x) != len(series.y) or len(series.x) < 2:
                return False, f"Series '{series.label}' has invalid coordinate data."
            finite_count = sum(
                1
                for x_value, y_value in zip(series.x, series.y)
                if _is_finite_number(x_value) and _is_finite_number(y_value)
            )
            if finite_count < 2:
                return False, f"Series '{series.label}' has no finite drawable segment."
        return True, ""

    def estimate_bytes(self, artifact: ScienceArtifact) -> int:
        if not artifact.graph:
            return 0
        if artifact.graph.surface:
            surface = artifact.graph.surface
            return (len(surface.x) + len(surface.y) + sum(len(row) for row in surface.z)) * 8
        return sum((len(series.x) + len(series.y)) * 8 for series in artifact.graph.series)


class PhysicsRendererPlugin:
    renderer_id = "physics.simulation"
    label = "Interactive 2D/3D physics"
    interactive = True

    def can_render(self, prompt: str) -> bool:
        return wants_physics(prompt)

    def render(self, prompt: str) -> ScienceArtifact | None:
        return build_physics_artifact(prompt)

    def validate(self, artifact: ScienceArtifact) -> tuple[bool, str]:
        physics = artifact.physics
        if artifact.kind != "physics" or physics is None:
            return False, "The physics engine did not return a simulation artifact."
        width, height = physics.bounds
        if width <= 0 or height <= 0:
            return False, "The simulation bounds are invalid."
        if not physics.particles:
            return False, "The simulation contains no physical bodies."
        for particle in physics.particles:
            values = (
                particle.x,
                particle.y,
                particle.vx,
                particle.vy,
                particle.radius,
                particle.mass,
            )
            if physics.simulation_type == "particle-3d":
                values = (*values, particle.z, particle.vz)
            if not all(_is_finite_number(value) for value in values):
                return False, "The simulation contains non-finite body data."
            if particle.radius <= 0 or particle.mass <= 0:
                return False, "The simulation contains a body with invalid mass or radius."
        return True, ""

    def estimate_bytes(self, artifact: ScienceArtifact) -> int:
        return len(artifact.physics.particles) * 64 if artifact.physics else 0


class MoleculeRendererPlugin:
    renderer_id = "chemistry.molecule"
    label = "Interactive molecular structure"
    interactive = True

    def can_render(self, prompt: str) -> bool:
        return wants_molecule(prompt)

    def render(self, prompt: str) -> ScienceArtifact | None:
        return build_molecule_artifact(prompt)

    def validate(self, artifact: ScienceArtifact) -> tuple[bool, str]:
        molecule = artifact.chemistry
        if artifact.kind != "chemistry" or molecule is None:
            return False, "The chemistry engine did not return a molecular artifact."
        if not molecule.atoms or not molecule.bonds:
            return False, "The molecule contains no renderable atoms or bonds."
        atom_ids = {atom.atom_id for atom in molecule.atoms}
        if len(atom_ids) != len(molecule.atoms) or molecule.central_atom not in atom_ids:
            return False, "The molecule contains an invalid atom topology."
        for atom in molecule.atoms:
            if not atom.element or not all(
                _is_finite_number(value) for value in (atom.x, atom.y, atom.z)
            ):
                return False, "The molecule contains invalid atom coordinates."
        for bond in molecule.bonds:
            if bond.first not in atom_ids or bond.second not in atom_ids:
                return False, "A molecular bond references a missing atom."
            if bond.first == bond.second or bond.order not in {1, 2, 3}:
                return False, "The molecule contains an invalid bond."
        if molecule.instruction.get("parameters", {}).get("source") != "curated-vsepr-library":
            return False, "The molecule was not produced by the validated structure library."
        return True, ""

    def estimate_bytes(self, artifact: ScienceArtifact) -> int:
        molecule = artifact.chemistry
        return (len(molecule.atoms) * 96 + len(molecule.bonds) * 32) if molecule else 0


class DiagramRendererPlugin:
    renderer_id = "diagram.structured"
    label = "Interactive structured diagram"
    interactive = True

    def can_render(self, prompt: str) -> bool:
        return wants_diagram(prompt)

    def render(self, prompt: str) -> ScienceArtifact | None:
        return build_diagram_artifact(prompt)

    def validate(self, artifact: ScienceArtifact) -> tuple[bool, str]:
        diagram = artifact.diagram
        if artifact.kind != "diagram" or diagram is None:
            return False, "The diagram engine did not return a structured artifact."
        if not diagram.nodes:
            return False, "The diagram contains no nodes."
        node_ids = {node.node_id for node in diagram.nodes}
        if len(node_ids) != len(diagram.nodes):
            return False, "The diagram contains duplicate node identifiers."
        if any(not node.label.strip() for node in diagram.nodes):
            return False, "The diagram contains an empty node."
        if any(edge.source not in node_ids or edge.target not in node_ids for edge in diagram.edges):
            return False, "A diagram edge references a missing node."
        return True, ""

    def estimate_bytes(self, artifact: ScienceArtifact) -> int:
        diagram = artifact.diagram
        return (len(diagram.nodes) * 128 + len(diagram.edges) * 96) if diagram else 0


class BiologyRendererPlugin:
    renderer_id = "biology.educational"
    label = "Interactive biology model"
    interactive = True

    def can_render(self, prompt: str) -> bool:
        return wants_biology(prompt)

    def render(self, prompt: str) -> ScienceArtifact | None:
        return build_biology_artifact(prompt)

    def validate(self, artifact: ScienceArtifact) -> tuple[bool, str]:
        biology = artifact.biology
        if artifact.kind != "biology" or biology is None:
            return False, "The biology engine did not return a model artifact."
        if len(biology.points) < 2 or not biology.labels:
            return False, "The biology model contains no renderable geometry."
        if any(
            not all(_is_finite_number(value) for value in point)
            for point in biology.points
        ):
            return False, "The biology model contains invalid coordinates."
        return True, ""

    def estimate_bytes(self, artifact: ScienceArtifact) -> int:
        biology = artifact.biology
        return len(biology.points) * 64 if biology else 0


class DataStructureRendererPlugin:
    renderer_id = "computer-science.data-structures"
    label = "Interactive data-structure lab"
    interactive = True

    def can_render(self, prompt: str) -> bool:
        return wants_data_structures(prompt)

    def render(self, prompt: str) -> ScienceArtifact | None:
        return build_data_structure_artifact(prompt)

    def validate(self, artifact: ScienceArtifact) -> tuple[bool, str]:
        data = artifact.data_structures
        if artifact.kind != "data-structures" or data is None:
            return False, "The data-structure engine did not return a lab artifact."
        if not data.structures or not data.initial_values:
            return False, "The data-structure lab has no structures or values."
        return True, ""

    def estimate_bytes(self, artifact: ScienceArtifact) -> int:
        data = artifact.data_structures
        return (
            len(data.structures) * 256 + len(data.initial_values) * 16
            if data
            else 0
        )


class RendererRegistry:
    def __init__(self):
        self._plugins: dict[str, RendererPlugin] = {}
        self._lock = threading.RLock()

    def register(self, plugin: RendererPlugin) -> None:
        with self._lock:
            if plugin.renderer_id in self._plugins:
                raise ValueError(f"Renderer already registered: {plugin.renderer_id}")
            self._plugins[plugin.renderer_id] = plugin

    def unregister(self, renderer_id: str) -> None:
        with self._lock:
            self._plugins.pop(renderer_id, None)

    def get(self, renderer_id: str) -> RendererPlugin | None:
        with self._lock:
            return self._plugins.get(renderer_id)

    def select(self, prompt: str) -> RendererPlugin | None:
        with self._lock:
            plugins = tuple(self._plugins.values())
        return next((plugin for plugin in plugins if plugin.can_render(prompt)), None)

    def capabilities(self) -> list[RendererCapability]:
        with self._lock:
            plugins = tuple(self._plugins.values())
        return [
            RendererCapability(
                renderer_id=plugin.renderer_id,
                label=plugin.label,
                available=True,
                interactive=plugin.interactive,
                backend="PySide6 raster/vector canvas",
            )
            for plugin in plugins
        ]


class ResourceManager:
    def __init__(self, max_bytes: int = 256 * 1024 * 1024):
        self.max_bytes = max(8 * 1024 * 1024, int(max_bytes))
        self._cache: OrderedDict[str, tuple[ScienceArtifact, int]] = OrderedDict()
        self._used_bytes = 0
        self._lock = threading.RLock()

    @staticmethod
    def key(renderer_id: str, prompt: str) -> str:
        payload = f"{renderer_id}\0{prompt.strip()}".encode("utf-8", errors="replace")
        return hashlib.sha256(payload).hexdigest()

    def get(self, cache_key: str) -> ScienceArtifact | None:
        with self._lock:
            cached = self._cache.pop(cache_key, None)
            if cached is None:
                return None
            self._cache[cache_key] = cached
            return copy.deepcopy(cached[0])

    def put(self, cache_key: str, artifact: ScienceArtifact, size_bytes: int) -> None:
        size_bytes = max(1, int(size_bytes))
        if size_bytes > self.max_bytes:
            return
        with self._lock:
            previous = self._cache.pop(cache_key, None)
            if previous:
                self._used_bytes -= previous[1]
            while self._cache and self._used_bytes + size_bytes > self.max_bytes:
                _key, (_artifact, removed_size) = self._cache.popitem(last=False)
                self._used_bytes -= removed_size
            self._cache[cache_key] = (copy.deepcopy(artifact), size_bytes)
            self._used_bytes += size_bytes

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._used_bytes = 0

    @property
    def used_bytes(self) -> int:
        with self._lock:
            return self._used_bytes


class RenderScheduler:
    def __init__(self, max_workers: int = 2):
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, min(4, max_workers)),
            thread_name_prefix="morice-render",
        )
        self._futures: dict[str, Future] = {}
        self._lock = threading.RLock()

    def submit(self, job_id: str, function, *args, **kwargs) -> Future:
        future = self._executor.submit(function, *args, **kwargs)
        with self._lock:
            self._futures[job_id] = future
        future.add_done_callback(lambda _future: self._forget(job_id))
        return future

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            future = self._futures.get(job_id)
        return bool(future and future.cancel())

    def _forget(self, job_id: str) -> None:
        with self._lock:
            self._futures.pop(job_id, None)

    @property
    def queued_jobs(self) -> int:
        with self._lock:
            return sum(1 for future in self._futures.values() if not future.done())

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


class CapabilityDetector:
    def snapshot(self) -> dict:
        return {
            "platform": platform.system(),
            "platformRelease": platform.release(),
            "cpuThreads": os.cpu_count() or 1,
            "renderBackend": "PySide6 CPU painter",
            "gpuAcceleration": False,
            "gpuReason": (
                "The validated desktop canvases currently use deterministic Qt CPU rendering. "
                "GPU-specific backends are reported unavailable instead of being claimed."
            ),
        }


UNAVAILABLE_RENDERERS = {
    "model.generic-3d": "The general 3D renderer is not installed yet.",
    "viewer.document": "The requested document viewer is not installed in the chat renderer yet.",
}


class VisualizationManager:
    def __init__(
        self,
        registry: RendererRegistry | None = None,
        resources: ResourceManager | None = None,
        scheduler: RenderScheduler | None = None,
    ):
        self.registry = registry or RendererRegistry()
        if registry is None:
            self.registry.register(BiologyRendererPlugin())
            self.registry.register(DataStructureRendererPlugin())
            self.registry.register(GraphRendererPlugin())
            self.registry.register(PhysicsRendererPlugin())
            self.registry.register(MoleculeRendererPlugin())
            self.registry.register(DiagramRendererPlugin())
        self.resources = resources or ResourceManager()
        self.scheduler = scheduler or RenderScheduler()
        self.capability_detector = CapabilityDetector()

    def decide(self, prompt: str) -> VisualizationDecision | None:
        text = (prompt or "").strip()
        if not text:
            return None
        plugin = self.registry.select(text)
        if plugin:
            reason = {
                "math.graph": "The request contains a drawable mathematical function.",
                "physics.simulation": "The request describes a supported dynamic physical system.",
                "chemistry.molecule": "The request names a molecule in the validated VSEPR structure library.",
                "diagram.structured": "The request maps to a validated structured-diagram template.",
                "biology.educational": "The request describes a supported biology model.",
                "computer-science.data-structures": "The request asks for interactive data-structure operations.",
            }.get(plugin.renderer_id, "A validated renderer supports this request.")
            return VisualizationDecision(plugin.renderer_id, reason, 1.0)

        lowered = text.lower()
        visual_verb = bool(
            re.search(
                r"\b(?:animate|diagram|draw|graph|model|plot|render|show|simulate|visuali[sz]e)\b",
                lowered,
            )
        )
        if not visual_verb:
            return None
        if any(
            marker in lowered
            for marker in {
                "biology",
                "cell",
                "chromosome",
                "dna",
                "double helix",
                "genetics",
                "neuron",
                "protein",
                "rna",
            }
        ):
            return VisualizationDecision(
                "biology.educational",
                "The request explicitly asks for a supported biology visualization.",
                0.97,
            )
        if any(
            marker in lowered
            for marker in {
                "avl tree",
                "binary search tree",
                "data structure",
                "hash table",
                "linked list",
                "queue",
                "stack",
            }
        ):
            return VisualizationDecision(
                "computer-science.data-structures",
                "The request explicitly asks for interactive data-structure operations.",
                0.97,
            )
        if any(
            marker in lowered
            for marker in {
                "atom",
                "bond",
                "chemistry",
                "electron density",
                "hybridization",
                "lewis structure",
                "molecule",
                "molecular",
                "vsepr",
            }
        ) or (
            "orbital" in lowered
            and any(marker in lowered for marker in {"atom", "electron", "quantum"})
        ):
            return VisualizationDecision(
                "chemistry.molecule",
                "The request explicitly asks for a chemistry visualization.",
                0.96,
            )
        if any(marker in lowered for marker in {"3d", "three-dimensional", "rotate the model"}):
            return VisualizationDecision(
                "model.generic-3d",
                "The request explicitly asks for a general 3D visualization.",
                0.94,
            )
        if any(marker in lowered for marker in {"pdf", "spreadsheet", "presentation", "document viewer"}):
            return VisualizationDecision(
                "viewer.document",
                "The request explicitly asks for an embedded document visualization.",
                0.9,
            )
        if any(
            marker in lowered
            for marker in {
                "ast",
                "class diagram",
                "er diagram",
                "flowchart",
                "mind map",
                "network topology",
                "sequence diagram",
                "timeline",
                "tree",
                "uml",
            }
        ):
            return VisualizationDecision(
                "diagram.structured",
                "The request explicitly asks for a structured diagram.",
                0.92,
            )
        return None

    def create_request(self, prompt: str, decision: VisualizationDecision) -> VisualizationRequest:
        return VisualizationRequest(uuid.uuid4().hex, prompt.strip(), decision)

    def submit(self, request: VisualizationRequest, progress: ProgressCallback) -> Future:
        return self.scheduler.submit(request.job_id, self.render, request, progress)

    def render(self, request: VisualizationRequest, progress: ProgressCallback) -> VisualizationResult:
        started = time.perf_counter()
        stages: list[str] = []

        def advance(stage: str, detail: str, percent: int) -> None:
            stages.append(stage)
            progress(stage, detail, percent)

        try:
            advance("Analyzing request", request.decision.reason, 8)
            plugin = self.registry.get(request.decision.renderer_id)
            if plugin is None:
                message = UNAVAILABLE_RENDERERS.get(
                    request.decision.renderer_id,
                    f"Renderer '{request.decision.renderer_id}' is not installed.",
                )
                advance("Renderer unavailable", message, 100)
                return VisualizationResult(
                    request.job_id,
                    "unsupported",
                    request.decision.renderer_id,
                    error=message,
                    duration_ms=(time.perf_counter() - started) * 1000,
                    stages=stages,
                )

            advance("Selecting renderer", plugin.label, 20)
            cache_key = self.resources.key(plugin.renderer_id, request.prompt)
            cached = self.resources.get(cache_key)
            if cached is not None:
                advance("Loading cached resources", "Using a validated local render artifact.", 76)
                valid, validation_error = plugin.validate(cached)
                if not valid:
                    self.resources.clear()
                    raise ValueError(validation_error)
                advance("Rendering output", "Preparing the interactive chat workspace.", 100)
                return VisualizationResult(
                    request.job_id,
                    "ready",
                    plugin.renderer_id,
                    artifact=cached,
                    duration_ms=(time.perf_counter() - started) * 1000,
                    validated=True,
                    from_cache=True,
                    stages=stages,
                )

            advance("Preparing data", "Parsing parameters and building deterministic render data.", 38)
            artifact = plugin.render(request.prompt)
            if artifact is None:
                raise ValueError(f"{plugin.label} could not parse this request into renderable data.")
            advance("Validating output", "Checking geometry, numeric values, and renderer contracts.", 68)
            valid, validation_error = plugin.validate(artifact)
            if not valid:
                raise ValueError(validation_error)
            self.resources.put(cache_key, artifact, plugin.estimate_bytes(artifact))
            advance("Rendering output", "Creating the interactive chat workspace.", 100)
            return VisualizationResult(
                request.job_id,
                "ready",
                plugin.renderer_id,
                artifact=artifact,
                duration_ms=(time.perf_counter() - started) * 1000,
                validated=True,
                stages=stages,
            )
        except Exception as exc:  # noqa: BLE001
            message = f"Rendering failed: {exc}"
            advance("Render failed", message, 100)
            return VisualizationResult(
                request.job_id,
                "failed",
                request.decision.renderer_id,
                error=message,
                duration_ms=(time.perf_counter() - started) * 1000,
                stages=stages,
            )

    def capabilities(self) -> list[RendererCapability]:
        capabilities = self.registry.capabilities()
        capabilities.extend(
            RendererCapability(
                renderer_id=renderer_id,
                label=renderer_id,
                available=False,
                interactive=True,
                backend="unavailable",
                reason=reason,
            )
            for renderer_id, reason in UNAVAILABLE_RENDERERS.items()
        )
        return capabilities

    def sanitize_model_reply(self, reply: str) -> str:
        text = (reply or "").strip()
        if not text:
            return text
        fake_pattern = re.compile(
            r"(?im)^\s*(?:\[|\()?\s*"
            r"(?:a\s+|the\s+)?(?:graph|simulation|visualization|model|diagram|window)"
            r".*?\b(?:appears?|displayed|opens?|rendered|shown)\b.*?(?:\]|\))?\s*$"
        )
        cleaned = fake_pattern.sub("", text)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        if cleaned:
            return cleaned
        return (
            "No visualization was rendered. The requested renderer did not produce a validated output, "
            "so MORICE will not pretend that one exists."
        )

    def shutdown(self) -> None:
        self.scheduler.shutdown()
        self.resources.clear()


def _is_finite_number(value) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return number == number and abs(number) != float("inf")
