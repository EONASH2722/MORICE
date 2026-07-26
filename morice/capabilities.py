from __future__ import annotations

import re
from dataclasses import dataclass

from .settings import normalize_emoji_level, normalize_maturity_level


@dataclass(frozen=True)
class CapabilitySection:
    title: str
    emoji: str
    items: tuple[str, ...]


CAPABILITY_SECTIONS = {
    "rendering": CapabilitySection(
        "Rendering and science",
        "📊",
        (
            "Interactive 2D function graphs with zoom, pan, hover inspection, roots, intercepts, extrema, and inflection points",
            "Polar, parametric, implicit, piecewise, and multi-equation graphs",
            "3D function surfaces with linked 2D height-map and 3D mesh views",
            "Live physics scenes for particles, projectile motion, pendulums, springs, waves, circular motion, and orbital motion",
            "Curated 2D and 3D molecular geometry views with atoms, bonds, labels, and VSEPR information",
            "Structured flow, networking, compiler, and process-state diagrams",
            "Rich Markdown, syntax-highlighted code, tables, and KaTeX mathematics",
        ),
    ),
    "project": CapabilitySection(
        "Project workspace",
        "💻",
        (
            "Create and edit complete project files inside a user-selected work folder",
            "Build websites, apps, games, scripts, and tools from a direct prompt",
            "Inspect a project tree and preview text, JSON, CSV, image, and PDF files",
            "Review file changes with added and removed lines before continuing",
            "Run safe project commands, inspect output, and keep a task queue",
            "Use folder-limited access or explicitly selected full access",
            "Use local-only context or Online+local research when the user enables it",
        ),
    ),
    "desktop": CapabilitySection(
        "Desktop assistant",
        "🖥️",
        (
            "Open applications, websites, files, and folders",
            "Search local files while skipping generated dependency folders",
            "Capture screenshots and organize recent files",
            "Report CPU, GPU, RAM, storage, network, and battery information",
            "Control supported media playback and system volume",
            "Preview local media in the workspace",
            "Ask for confirmation before sensitive actions such as closing applications",
        ),
    ),
    "models": CapabilitySection(
        "AI models",
        "🧠",
        (
            "Run supported local GGUF models through the local llama runtime",
            "Connect to a locally installed Ollama model",
            "Browse compatible GGUF models and inspect model metadata",
            "Detect GPU and VRAM, then estimate an appropriate run plan",
            "Validate a selected file before accepting it as an AI model",
            "Switch models in the app without changing MORICE's renderer pipeline",
        ),
    ),
    "files": CapabilitySection(
        "Files and rich content",
        "📁",
        (
            "Preview source code, plain text, Markdown, JSON, JSONL, and CSV files",
            "Display local images and PDFs inside the workspace",
            "Play supported local audio and video files",
            "Render code blocks with syntax highlighting and copy-friendly formatting",
            "Render inline and display mathematics with KaTeX",
            "Show project diffs, logs, trees, tables, and structured data",
        ),
    ),
}


_TOPIC_TERMS = {
    "rendering": {
        "render",
        "rendering",
        "renderings",
        "visual",
        "visualization",
        "visualizations",
        "graph",
        "graphs",
        "simulation",
        "simulations",
        "science",
    },
    "project": {
        "project",
        "projects",
        "coding",
        "code",
        "developer",
        "development",
        "website",
        "app",
        "game",
    },
    "desktop": {
        "desktop",
        "computer",
        "system",
        "windows",
        "assistant",
        "automation",
        "tool",
        "tools",
    },
    "models": {
        "model",
        "models",
        "gguf",
        "ollama",
        "gpu",
        "vram",
        "llm",
    },
    "files": {
        "file",
        "files",
        "format",
        "formats",
        "preview",
        "previews",
        "viewer",
        "viewers",
    },
}

_TYPO_ALIASES = {
    "capabilites": "capabilities",
    "capabilties": "capabilities",
    "capablities": "capabilities",
    "renderng": "rendering",
    "rendring": "rendering",
    "renering": "rendering",
    "visulization": "visualization",
    "visualisation": "visualization",
    "simlation": "simulation",
    "suport": "support",
    "suppport": "support",
    "modles": "models",
    "moddel": "model",
    "fiels": "files",
}


def emoji_preference_instruction(value: str) -> str:
    level = normalize_emoji_level(value)
    if level == "none":
        return (
            "Emoji preference: do not use emoji in prose. Never alter code, paths, "
            "structured data, or quoted user text to enforce this preference."
        )
    if level == "expressive":
        return (
            "Emoji preference: use a lively but readable amount of relevant emoji in "
            "headings and prose. Do not put emoji in code, paths, commands, or structured data."
        )
    return (
        "Emoji preference: use emoji sparingly, only where one improves scanning or tone. "
        "Do not put emoji in code, paths, commands, or structured data."
    )


def maturity_preference_instruction(value: str) -> str:
    level = normalize_maturity_level(value)
    truth_rule = (
        "Truth-first disagreement rule: user insistence is not evidence. Re-check the claim, "
        "reasoning, and available context. If the answer is still supported, say 'No' plainly "
        "and explain why instead of conceding, apologizing, or pretending to be wrong. If new "
        "evidence reveals a real mistake, correct it directly. State uncertainty honestly and "
        "never invent confidence."
    )
    if level == "full":
        tone_rule = (
            "Maturity setting: Full. Strong profanity is allowed when it naturally strengthens "
            "a blunt response, including during persistent disagreement. Do not use slurs, "
            "threats, targeted humiliation, or attacks on protected traits, and do not replace "
            "reasoning with insults."
        )
    elif level == "medium":
        tone_rule = (
            "Maturity setting: Medium. Occasional mild profanity is allowed when it fits the "
            "conversation, but keep disagreement focused on the claim. Do not use slurs, "
            "threats, targeted humiliation, or attacks on protected traits."
        )
    else:
        tone_rule = (
            "Maturity setting: None. Do not use profanity or mature wording. Be firm and direct "
            "when disagreeing without insulting the user."
        )
    return f"{truth_rule}\n{tone_rule}"


def _normalized_words(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9+]+", str(text or "").lower())
    return [_TYPO_ALIASES.get(word, word) for word in words]


def detect_capability_topic(text: str) -> str | None:
    words = _normalized_words(text)
    if not words:
        return None
    cleaned = " ".join(words)
    self_reference = bool(re.search(r"\b(?:you|your|morice)\b", cleaned))
    if not self_reference:
        return None

    asks_for_inventory = any(
        re.search(pattern, cleaned)
        for pattern in (
            r"\bwhat(?: all)? (?:can|could) you do\b",
            r"^what do you do(?:\s+(?:in|with|for)\b.*)?$",
            r"\b(?:what|which|list|describe|explain|tell|show)\b.*"
            r"\b(?:capabilit\w*|features?|supported)\b",
            r"\b(?:what|which|list)\b.*\b(?:can you|do you)\b.*"
            r"\b(?:render|support|open|handle|build|create|make)\w*\b",
            r"\b(?:what|which|list)\b.*"
            r"\b(?:render\w*|visual\w*|simulat\w*|projects?|coding|desktop|"
            r"tools?|models?|files?|formats?|previews?)\b.*"
            r"\b(?:can you do|do you support|can you render|can you build|"
            r"can you open|can you handle|can you make)\b",
        )
    )
    if not asks_for_inventory:
        return None

    word_set = set(words)
    for topic in ("rendering", "project", "desktop", "models", "files"):
        if word_set.intersection(_TOPIC_TERMS[topic]):
            return topic
    return "overview"


def _bullet_prefix(level: str, section: CapabilitySection, index: int) -> str:
    if level == "expressive":
        choices = ("•", "◦", "▪")
        return f"{section.emoji} {choices[index % len(choices)]}"
    return "-"


def capability_answer(topic: str, emoji_level: str = "medium") -> str:
    level = normalize_emoji_level(emoji_level)
    selected = (
        [CAPABILITY_SECTIONS[topic]]
        if topic in CAPABILITY_SECTIONS
        else list(CAPABILITY_SECTIONS.values())
    )
    lines: list[str] = []
    if topic == "overview":
        heading = "MORICE capabilities"
        lines.append(f"{'✨ ' if level != 'none' else ''}**{heading}**")
        lines.append(
            "I can handle normal chat, real visualizations, local project work, "
            "desktop tools, rich file previews, and user-selected local AI models."
        )
    else:
        section = selected[0]
        lines.append(
            f"{section.emoji + ' ' if level != 'none' else ''}**{section.title}**"
        )

    for section in selected:
        if topic == "overview":
            lines.append("")
            lines.append(
                f"{section.emoji + ' ' if level != 'none' else ''}**{section.title}**"
            )
        for index, item in enumerate(section.items):
            lines.append(f"{_bullet_prefix(level, section, index)} {item}")

    lines.extend(
        (
            "",
            "These are the renderers and tools currently implemented. If a requested "
            "renderer is unavailable or fails validation, MORICE reports that honestly "
            "instead of pretending an output was created.",
        )
    )
    return "\n".join(lines)
