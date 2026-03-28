import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

KB_DIR = os.getenv("MORICE_KB_DIR", r"D:\FOOD FOR MORICE")
KB_TOPK = int(os.getenv("MORICE_KB_TOPK", "3"))
CHUNK_SIZE = int(os.getenv("MORICE_KB_CHUNK", "1000"))
CHUNK_OVERLAP = int(os.getenv("MORICE_KB_OVERLAP", "120"))
MAX_FILE_MB = int(os.getenv("MORICE_KB_MAX_MB", "10"))
MAX_CHUNKS = int(os.getenv("MORICE_KB_MAX_CHUNKS", "200"))
KB_DISABLED = os.getenv("MORICE_KB_DISABLE", "0") == "1"
KB_REQUIRE_TAG = os.getenv("MORICE_KB_REQUIRE_TAG", "1") == "1"
KB_PRELOAD = os.getenv("MORICE_KB_PRELOAD", "0") == "1"


@dataclass
class Chunk:
    source: str
    text: str
    tokens: set


_cached_chunks: List[Chunk] | None = None


def _tokenize(text: str) -> set:
    return {t for t in re.findall(r"[a-zA-Z0-9_]{3,}", text.lower())}


def _chunk_text(text: str):
    start = 0
    length = len(text)
    overlap = max(0, min(CHUNK_OVERLAP, max(CHUNK_SIZE - 1, 0)))
    while start < length:
        end = min(start + CHUNK_SIZE, length)
        chunk = text[start:end].strip()
        if chunk:
            yield chunk
        start = end - overlap
        if start < 0:
            start = 0
        if start >= length:
            break


def _load_chunks() -> List[Chunk]:
    chunks: List[Chunk] = []
    root = Path(KB_DIR)
    if not root.exists():
        return chunks

    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if path.suffix.lower() not in {".txt", ".md"}:
            continue
        try:
            if path.stat().st_size > MAX_FILE_MB * 1024 * 1024:
                continue
        except OSError:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for chunk in _chunk_text(text):
            chunks.append(Chunk(source=str(path), text=chunk, tokens=_tokenize(chunk)))
            if len(chunks) >= MAX_CHUNKS:
                return chunks

    return chunks


def load_knowledge() -> int:
    global _cached_chunks
    if KB_DISABLED:
        _cached_chunks = []
        return 0
    try:
        _cached_chunks = _load_chunks()
    except MemoryError:
        _cached_chunks = []
        return 0
    return len(_cached_chunks)


def retrieve_context(query: str) -> str:
    global _cached_chunks
    if _cached_chunks is None:
        try:
            _cached_chunks = _load_chunks()
        except MemoryError:
            _cached_chunks = []
            return ""

    if not _cached_chunks:
        return ""

    q_tokens = _tokenize(query)
    if not q_tokens:
        return ""

    scored = []
    for chunk in _cached_chunks:
        score = len(q_tokens & chunk.tokens)
        if score:
            scored.append((score, chunk))

    if not scored:
        return ""

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [chunk for _, chunk in scored[:KB_TOPK]]

    sections = []
    for chunk in top:
        sections.append(f"Source: {chunk.source}\n{chunk.text}")

    return "\n\n".join(sections)


def should_use_context(query: str) -> bool:
    if KB_DISABLED:
        return False
    if not KB_REQUIRE_TAG:
        return True
    cleaned = query.lower()
    return "notes" in cleaned or "from my notes" in cleaned or "@notes" in cleaned


def should_preload() -> bool:
    return KB_PRELOAD and not KB_DISABLED


def search_notes(term: str, max_hits: int = 10):
    term = (term or "").strip().lower()
    if not term:
        return []
    root = Path(KB_DIR)
    if not root.exists():
        return []

    hits = []
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if path.suffix.lower() not in {".txt", ".md"}:
            continue
        try:
            if path.stat().st_size > MAX_FILE_MB * 1024 * 1024:
                continue
        except OSError:
            continue
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    if term in line.lower():
                        snippet = line.strip()
                        if len(snippet) > 200:
                            snippet = snippet[:200].rstrip() + "..."
                        hits.append({"source": str(path), "text": snippet})
                        if len(hits) >= max_hits:
                            return hits
        except OSError:
            continue
    return hits
