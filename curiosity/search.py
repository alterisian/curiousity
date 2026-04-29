import json
import os
import urllib.error
import urllib.parse
import urllib.request


def fetch_snippets(query: str, max_results: int = 5) -> list[str]:
    api_key = os.environ.get("BRAVE_API_KEY")
    if not api_key:
        raise ValueError("BRAVE_API_KEY environment variable is not set.")

    url = (
        "https://api.search.brave.com/res/v1/web/search"
        f"?q={urllib.parse.quote(query)}&count={max_results}"
    )
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise ValueError(f"Brave API error {e.code}: {e.reason}") from e

    results = body.get("web", {}).get("results", [])
    snippets = []
    for r in results[:max_results]:
        text = r.get("description") or r.get("extra_snippets", [""])[0]
        if text and text.strip():
            snippets.append(text.strip())
    return snippets
