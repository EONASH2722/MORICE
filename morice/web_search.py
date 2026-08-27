import html
import json
import re
import socket
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass


USER_AGENT = "MORICE/1.0 (+https://github.com/EONASH2722/MORICE)"


@dataclass(frozen=True)
class WebDecision:
    """A small, explainable pre-model decision for live information.

    This is deliberately a high-precision fast path. Ambiguous requests stay
    local instead of paying a network penalty or leaking unrelated text.
    """

    required: bool
    query: str = ""
    reason: str = ""


_CONNECTIVITY_LOCK = threading.Lock()
_CONNECTIVITY_VALUE = False
_CONNECTIVITY_CHECKED_AT = 0.0
_CONNECTIVITY_TTL_SECONDS = 15.0


def internet_available(*, timeout: float = 0.35, force: bool = False) -> bool:
    """Return cached internet reachability without opening a browser.

    The short socket probe keeps offline requests from waiting for the web
    search timeout. Search still handles false positives safely.
    """

    global _CONNECTIVITY_CHECKED_AT, _CONNECTIVITY_VALUE
    now = time.monotonic()
    with _CONNECTIVITY_LOCK:
        if not force and now - _CONNECTIVITY_CHECKED_AT < _CONNECTIVITY_TTL_SECONDS:
            return _CONNECTIVITY_VALUE
    reachable = False
    try:
        with socket.create_connection(("1.1.1.1", 443), timeout=max(0.05, timeout)):
            reachable = True
    except OSError:
        reachable = False
    with _CONNECTIVITY_LOCK:
        _CONNECTIVITY_VALUE = reachable
        _CONNECTIVITY_CHECKED_AT = now
    return reachable


def infer_web_need(text: str) -> WebDecision:
    """Infer whether the answer materially depends on live/external data.

    The examples are represented as semantic signals (freshness, live state,
    sourcing and explicit research), not one command per feature. Ordinary
    timeless questions remain local and the existing direct-control router is
    unaffected.
    """

    clean = " ".join(str(text or "").split())
    if not clean:
        return WebDecision(False)
    lowered = clean.casefold()
    explicit = re.match(r"^(?:@web\s*|web:\s*)(.+)$", clean, re.IGNORECASE)
    if explicit:
        query = explicit.group(1).strip()
        return WebDecision(bool(query), query, "explicit-web-hint")

    score = 0
    reasons: list[str] = []
    if re.search(
        r"\b(?:search|research|browse|look\s+up|find\s+online|verify\s+online|"
        r"source|sources|citation|citations)\b",
        lowered,
    ):
        score += 3
        reasons.append("external-research")
    if re.search(
        r"\b(?:latest|newest|current|currently|today|tonight|tomorrow|yesterday|"
        r"this\s+(?:week|month|year)|recent|breaking|live|real[- ]?time)\b",
        lowered,
    ):
        score += 2
        reasons.append("freshness")
    if re.search(
        r"\b(?:news|weather|forecast|price|prices|stock|market|exchange\s+rate|"
        r"score|scores|standings|schedule|traffic|outage|availability|release|"
        r"version|update|security\s+advisory)\b",
        lowered,
    ):
        score += 2
        reasons.append("live-domain")
    if re.search(
        r"\b(?:who\s+(?:is|runs|leads)|president|prime\s+minister|chief\s+executive|"
        r"\bceo\b|governor|mayor)\b",
        lowered,
    ):
        score += 2
        reasons.append("changing-office-holder")
    if re.search(r"https?://|\bwww\.|\.[a-z]{2,}(?:/|\b)", lowered):
        score += 3
        reasons.append("specific-web-resource")
    if re.search(r"\b(?:my\s+notes?|from\s+my\s+notes?|my\s+files?|this\s+project|my\s+pc)\b", lowered):
        score -= 3
        reasons.append("local-context")
    if re.match(r"^(?:explain|teach|define|what\s+is|how\s+does|why\s+does)\b", lowered):
        score -= 1
        reasons.append("timeless-question")
    return WebDecision(
        score >= 2,
        clean if score >= 2 else "",
        ",".join(reasons),
    )


def _fetch_json(url: str, timeout: int) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _fetch_text(url: str, timeout: int) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _decode_html(text: str) -> str:
    replacements = {
        "&amp;": "&",
        "&lt;": "<",
        "&gt;": ">",
        "&quot;": '"',
        "&#39;": "'",
        "&#x27;": "'",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _strip_html(text: str) -> str:
    return _decode_html(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))).strip()


def _clean_result_url(raw_url: str) -> str:
    decoded = _decode_html(raw_url)
    parsed = urllib.parse.urlparse(decoded)
    params = urllib.parse.parse_qs(parsed.query)
    if "uddg" in params and params["uddg"]:
        return urllib.parse.unquote(params["uddg"][0])
    return decoded


def _duckduckgo_html(query: str, timeout: int) -> str:
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    try:
        html = _fetch_text(url, timeout)
    except Exception:
        return ""

    results = []
    pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?'
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(html):
        title = _strip_html(match.group(2))
        link = _clean_result_url(match.group(1))
        snippet = _strip_html(match.group(3))
        if title and link.startswith(("http://", "https://")):
            results.append(f"{title}\n{snippet}\nSource: {link}")
        if len(results) >= 5:
            break

    return "\n\n".join(results)


def _duckduckgo(query: str, timeout: int) -> str:
    params = {
        "q": query,
        "format": "json",
        "no_redirect": 1,
        "no_html": 1,
    }
    url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode(params)
    try:
        data = _fetch_json(url, timeout)
    except Exception:
        return ""

    parts = []
    abstract = data.get("AbstractText", "")
    if abstract:
        parts.append(f"Summary: {abstract}")

    related = data.get("RelatedTopics", [])
    snippets = []
    for item in related:
        if isinstance(item, dict) and item.get("Text"):
            snippets.append(item["Text"])
        if len(snippets) >= 5:
            break
    if snippets:
        parts.append("Related: " + " | ".join(snippets))

    return "\n".join(parts).strip()


def _bing_rss(query: str, timeout: int) -> str:
    """Use Bing's RSS-shaped response as a resilient source-linked fallback."""

    url = "https://www.bing.com/search?" + urllib.parse.urlencode(
        {"q": query, "format": "rss"}
    )
    try:
        payload = _fetch_text(url, timeout)
        root = ET.fromstring(payload)
    except (ET.ParseError, OSError, ValueError):
        return ""
    results: list[str] = []
    for item in root.findall(".//item"):
        title = html.unescape((item.findtext("title") or "").strip())
        link = (item.findtext("link") or "").strip()
        description = _strip_html(
            html.unescape((item.findtext("description") or "").strip())
        )
        if title and link.startswith(("http://", "https://")):
            results.append(f"{title}\n{description}\nSource: {link}")
        if len(results) >= 5:
            break
    return "\n\n".join(results)


def _wikipedia(query: str, timeout: int) -> str:
    search_params = {
        "action": "opensearch",
        "search": query,
        "limit": 1,
        "namespace": 0,
        "format": "json",
    }
    search_url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(search_params)
    try:
        data = _fetch_json(search_url, timeout)
    except Exception:
        return ""

    if not isinstance(data, list) or len(data) < 2 or not data[1]:
        return ""

    title = data[1][0]
    page_url = data[3][0] if len(data) > 3 and data[3] else ""
    summary_url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title)
    try:
        summary = _fetch_json(summary_url, timeout)
    except Exception:
        return ""

    extract = summary.get("extract", "").strip()
    if not extract:
        return ""

    source_line = f"Source: {page_url}" if page_url else ""
    return "\n".join([f"Wikipedia: {extract}", source_line]).strip()


def search_web(query: str, timeout: int = 10) -> str:
    if not query:
        return ""

    result = _duckduckgo_html(query, timeout)
    if result:
        return result

    result = _duckduckgo(query, timeout)
    if result:
        return result

    result = _bing_rss(query, timeout)
    if result:
        return result

    result = _wikipedia(query, timeout)
    if result:
        return result

    return ""
