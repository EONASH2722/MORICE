"""Non-activating diagnostics for the existing RuntimeServices HealthReport."""
from __future__ import annotations


def subsystem_checks(runtime, check):
    rows = [check("Capability Kernel", "healthy" if not runtime.kernel._closed else "disabled",
        "Shared execution, permission, resource and verification authorities.", category="kernel"),
        check("Parallel agents", "healthy" if not runtime.agents._closed else "disabled",
            f"{len(runtime.agents.roles.all())} roles; drivers initialized: {runtime.agents._drivers is not None}.", category="agents"),
        check("Verified actions", "degraded" if runtime.actions.journal.load_error else "healthy",
            runtime.actions.journal.load_error or f"Durable journal; {len(runtime.actions.journal.interrupted())} interrupted attempts require observation.", category="actions")]
    for name, category, service in (
        ("Project Builder", "builder", runtime.autonomous_builder._project_runtime),
        ("Research Lab", "research", runtime._research_runtime),
        ("Device Mesh", "mesh", runtime._device_mesh),
        ("Ambient", "ambient", runtime._ambient_service),
        ("Generative Media Lab", "media", getattr(runtime, "_media_lab", None))):
        initialized = service is not None
        enabled = getattr(service, "enabled", initialized) if initialized else False
        rows.append(check(name, "healthy" if enabled else "disabled",
            "Initialized; runtime evidence is checked per action." if enabled else "Dormant or disabled; diagnostics do not initialize this subsystem.", category=category))
    ambient = runtime._ambient_service
    rows.extend((check("Connectors", "disabled" if ambient is None or not ambient.connectors.providers else "degraded",
        "No configured connector." if ambient is None or not ambient.connectors.providers else
        "Configured providers require individual connectivity and authorization checks.", category="connectors"),
        check("Defensive security", "healthy" if ambient and ambient.security.enabled else "disabled",
            "Scoped monitoring enabled." if ambient and ambient.security.enabled else "Monitoring is opt-in and currently disabled.", category="security"),
        check("Voice", "degraded" if runtime.voice.config.enabled else "disabled",
            "Provider configured; live audio availability requires an explicit request." if runtime.voice.config.enabled else "Speech output disabled.", category="voice"),
        check("Semantic vision", "degraded", "Capture and grounded adapters exist; arbitrary screen understanding requires an available configured vision provider.", category="vision"),
        check("Resource leases", "healthy", f"{len(runtime.kernel.resources.snapshot())} current leases; physical work retains leases until cleanup.", category="resources")))
    return tuple(rows)
