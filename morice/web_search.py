import json
import urllib.parse
import urllib.request


USER_AGENT = "MORICE/1.0 (+https://github.com/EONASH2722/MORICE)"


def _fetch_json(url: str, timeout: int) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


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

    result = _duckduckgo(query, timeout)
    if result:
        return result

    result = _wikipedia(query, timeout)
    if result:
        return result

    return ""
