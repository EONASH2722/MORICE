import json
import re
import urllib.parse
import urllib.request


USER_AGENT = "MORICE/1.0 (+https://github.com/EONASH2722/MORICE)"


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

    result = _wikipedia(query, timeout)
    if result:
        return result

    return ""
