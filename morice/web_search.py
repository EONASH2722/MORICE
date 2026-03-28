import json
import urllib.parse
import urllib.request


def search_web(query: str, timeout: int = 10) -> str:
    if not query:
        return ""
    params = {
        "q": query,
        "format": "json",
        "no_redirect": 1,
        "no_html": 1,
    }
    url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
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

    return "\n".join(parts)
