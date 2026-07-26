from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from .agent_types import AgentPlan, AgentSubtask, ExecutionStage, IntentType


_INTENT_PATTERNS: tuple[tuple[IntentType, tuple[str, ...]], ...] = (
    (IntentType.PROJECT_MODIFICATION, (
        r"\b(build|create|make|implement|refactor|fix|update|modify)\b.*\b(app|game|website|project|code|repo|repository)\b",
        r"\b(project mode|work folder|codebase)\b",
    )),
    (IntentType.FILE_EDITING, (
        r"\b(edit|write|rename|move|delete|overwrite|patch)\b.*\b(file|folder|directory)\b",
    )),
    (IntentType.FILE_SEARCH, (
        r"\b(find|locate|search)\b.*\b(file|folder|directory|text|symbol)\b",
    )),
    (IntentType.INTERNET_SEARCH, (
        r"\b(search|browse|look up|online|web|internet|latest|current)\b",
    )),
    (IntentType.TERMINAL_TASK, (
        r"\b(run|execute|terminal|command|shell|powershell|cmd|build|compile|test)\b",
    )),
    (IntentType.DESKTOP_CONTROL, (
        r"\b(open|close|minimize|maximize|click|type)\b.*\b(app|window|desktop|browser)\b",
    )),
    (IntentType.VISUALIZATION, (
        r"\b(plot|graph|visuali[sz]e|diagram|chart|render|draw|flowchart)\b",
    )),
    (IntentType.SIMULATION, (
        r"\b(simulat|particle|physics engine|animate|animation)\w*\b",
    )),
    (IntentType.MATHEMATICS, (
        r"\b(equation|integral|derivative|matrix|algebra|calculus|geometry|probability)\b",
        r"\by\s*=",
    )),
    (IntentType.PHYSICS, (
        r"\b(physics|gravity|velocity|acceleration|force|momentum|orbit|pendulum|wave)\b",
    )),
    (IntentType.CHEMISTRY, (
        r"\b(chemistry|molecule|atom|bond|reaction|vsepr|lewis|orbital|titration)\b",
    )),
    (IntentType.BIOLOGY, (
        r"\b(biology|cell|dna|rna|organ|anatomy|genetic|protein|ecosystem)\b",
    )),
    (IntentType.IMAGE_ANALYSIS, (
        r"\b(image|photo|picture|screenshot)\b.*\b(analy[sz]e|inspect|read|explain)\b",
    )),
    (IntentType.DOCUMENT_ANALYSIS, (
        r"\b(pdf|document|docx|spreadsheet|presentation)\b.*\b(analy[sz]e|inspect|read|summari[sz]e)\b",
    )),
    (IntentType.TRANSLATION, (r"\b(translat|translation)\w*\b",)),
    (IntentType.SUMMARIZATION, (r"\b(summari[sz]e|summary|condense)\b",)),
    (IntentType.DATA_ANALYSIS, (
        r"\b(data|dataset|csv|statistics|trend|correlation|regression)\b",
    )),
    (IntentType.PLANNING, (r"\b(plan|roadmap|strategy|steps)\b",)),
    (IntentType.REASONING, (r"\b(reason|explain why|analy[sz]e|compare|prove)\b",)),
    (IntentType.CODING, (
        r"\b(code|coding|python|typescript|javascript|rust|java|c\+\+|html|css|sql)\b",
    )),
)


@dataclass(frozen=True)
class IntentMatch:
    intent: IntentType
    confidence: float
    evidence: tuple[str, ...]


class IntentRouter:
    def classify(self, request: str) -> tuple[IntentMatch, ...]:
        clean = " ".join((request or "").lower().split())
        matches: list[IntentMatch] = []
        for intent, patterns in _INTENT_PATTERNS:
            evidence = tuple(
                match.group(0)
                for pattern in patterns
                if (match := re.search(pattern, clean, flags=re.IGNORECASE))
            )
            if evidence:
                confidence = min(0.98, 0.64 + (0.12 * len(evidence)))
                matches.append(IntentMatch(intent, confidence, evidence))
        if not matches:
            matches.append(IntentMatch(IntentType.GENERAL_CHAT, 0.72, ("default",)))
        if any(match.intent == IntentType.PROJECT_MODIFICATION for match in matches):
            if not any(match.intent == IntentType.CODING for match in matches):
                matches.append(IntentMatch(IntentType.CODING, 0.68, ("project work",)))
        return tuple(matches)

    def plan(self, request: str) -> AgentPlan:
        request_id = uuid.uuid4().hex
        matches = self.classify(request)
        subtasks: list[AgentSubtask] = []
        seen: set[IntentType] = set()
        for match in matches:
            if match.intent in seen:
                continue
            seen.add(match.intent)
            suggested_tools = self._suggest_tools(match.intent)
            subtasks.append(
                AgentSubtask(
                    subtask_id=f"{request_id}:{len(subtasks) + 1}",
                    title=match.intent.value.replace("_", " ").title(),
                    intent=match.intent,
                    description=self._description(match.intent),
                    dependencies=(
                        (subtasks[-1].subtask_id,) if subtasks and self._is_action(match.intent) else ()
                    ),
                    suggested_tools=suggested_tools,
                )
            )
        public_summary = tuple(
            subtask.description for subtask in subtasks if subtask.intent != IntentType.GENERAL_CHAT
        )
        return AgentPlan(
            request_id=request_id,
            request=request,
            intents=tuple(subtask.intent for subtask in subtasks),
            subtasks=tuple(subtasks),
            stages=tuple(ExecutionStage),
            public_summary=public_summary,
        )

    @staticmethod
    def _is_action(intent: IntentType) -> bool:
        return intent in {
            IntentType.PROJECT_MODIFICATION,
            IntentType.FILE_EDITING,
            IntentType.TERMINAL_TASK,
            IntentType.DESKTOP_CONTROL,
        }

    @staticmethod
    def _suggest_tools(intent: IntentType) -> tuple[str, ...]:
        return {
            IntentType.FILE_SEARCH: ("filesystem.search",),
            IntentType.FILE_EDITING: ("filesystem.patch",),
            IntentType.PROJECT_MODIFICATION: ("project.index", "filesystem.patch"),
            IntentType.TERMINAL_TASK: ("terminal.run",),
            IntentType.CODING: ("project.index",),
            IntentType.VISUALIZATION: ("renderer.inspect",),
            IntentType.SIMULATION: ("renderer.inspect",),
            IntentType.INTERNET_SEARCH: ("network.search",),
        }.get(intent, ())

    @staticmethod
    def _description(intent: IntentType) -> str:
        labels = {
            IntentType.PROJECT_MODIFICATION: "Inspect the project, prepare a patch, then verify it.",
            IntentType.FILE_EDITING: "Validate and preview requested file changes.",
            IntentType.FILE_SEARCH: "Search the permitted workspace and return real matches.",
            IntentType.TERMINAL_TASK: "Run the requested command with captured output and an exit code.",
            IntentType.VISUALIZATION: "Select and validate a real renderer before claiming a visual.",
            IntentType.SIMULATION: "Prepare deterministic simulation data and validate the renderer.",
            IntentType.INTERNET_SEARCH: "Retrieve current sources and preserve source metadata.",
        }
        return labels.get(intent, f"Handle the {intent.value.replace('_', ' ')} portion of the request.")
