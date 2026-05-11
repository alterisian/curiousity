import urllib.parse

EXTRACTION_PROMPT = """\
You are a knowledge extraction engine.
Given the input text, extract:
  - entities: list of {{id, name, type, confidence}}
  - facts: list of {{id, subject_id, predicate, object_id, confidence}}
  - uncertainties: list of strings describing missing knowledge

All confidence values must be between 0.0 and 1.0.
Respond with valid JSON only. No commentary.

Input: {text}
"""

CONSOLIDATION_PROMPT = """\
You are a knowledge consolidation engine.
Given the staged facts and entities below, merge duplicates and overlapping items
into canonical form. Increase confidence when multiple sources agree.
Respond with valid JSON only: {{"entities": [...], "facts": [...]}}.

Staged: {staged_json}
"""

CURIOSITY_PROMPT = """\
You are a curiosity-driven knowledge agent.
Given the current knowledge graph below, identify gaps, contradictions, and
missing links. For each, generate a specific question.
Respond with valid JSON only: {{"questions": [{{question, uncertainty, priority}}]}}.

Knowledge: {knowledge_json}
"""


def call_llm(prompt: str) -> dict:
    import json as _json
    import os
    import urllib.request
    import urllib.error
    from curiosity.logger import log_llm_call

    api_key = os.environ.get("MISTRAL_API_KEY")
    base_uri = os.environ.get("CURIOUSITY_LLM_BASE_URI")
    if not base_uri:
        base_uri = "https://api.mistral.ai/"
        if not api_key:
            raise ValueError("MISTRAL_API_KEY environment variable is not set.")

    # request timeout in seconds
    llm_timeout = int(os.environ.get("CURIOUSITY_LLM_TIMEOUT") or 30)

    headers = {
        "Content-Type": "application/json",
    }

    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = _json.dumps({
        "model": "mistral-small-latest",
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(
        urllib.parse.urljoin(base_uri, "/v1/chat/completions"),
        data=payload,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=llm_timeout) as resp:
            body = _json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise ValueError(f"Mistral API error {e.code}: {e.reason}") from e

    content = body["choices"][0]["message"]["content"]
    # Log raw LLM response and prompt
    try:
        log_llm_call(prompt, content)
    except Exception:
        pass
    try:
        return _json.loads(content)
    except _json.JSONDecodeError as e:
        raise ValueError(f"LLM returned invalid JSON: {e}") from e


def _validate_extraction_output(data: dict) -> None:
    assert "entities" in data,      "Extraction missing 'entities' key"
    assert "facts" in data,         "Extraction missing 'facts' key"
    assert "uncertainties" in data, "Extraction missing 'uncertainties' key"
    for e in data["entities"]:
        assert "name" in e,       f"Entity missing 'name': {e}"
        assert "confidence" in e, f"Entity missing 'confidence': {e}"
        assert 0.0 <= e["confidence"] <= 1.0, \
            f"Entity confidence out of range: {e['confidence']}"
    for f in data["facts"]:
        for key in ("subject_id", "predicate", "object_id", "confidence"):
            assert key in f, f"Fact missing '{key}': {f}"
        assert 0.0 <= f["confidence"] <= 1.0, \
            f"Fact confidence out of range: {f['confidence']}"


def extract_knowledge(text: str, llm_fn=None) -> dict:
    if llm_fn is None:
        llm_fn = call_llm
    raw = llm_fn(EXTRACTION_PROMPT.format(text=text))
    _validate_extraction_output(raw)
    return raw


def _validate_consolidation_output(data: dict) -> None:
    assert "entities" in data, "Consolidation missing 'entities' key"
    assert "facts" in data,    "Consolidation missing 'facts' key"


def consolidate(staged: list[dict], llm_fn=None) -> dict:
    import json
    if llm_fn is None:
        llm_fn = call_llm
    raw = llm_fn(CONSOLIDATION_PROMPT.format(staged_json=json.dumps(staged, ensure_ascii=False)))
    _validate_consolidation_output(raw)
    return raw


def _validate_question(q: dict) -> None:
    for key in ("question", "uncertainty", "priority"):
        assert key in q, f"Question missing '{key}': {q}"
    assert 0.0 <= q["uncertainty"] <= 1.0, \
        f"Question uncertainty out of range: {q['uncertainty']}"
    assert isinstance(q["question"], str) and q["question"].strip(), \
        "Question text is empty"


def generate_curiosity(knowledge: dict, llm_fn=None) -> list[dict]:
    import json
    if llm_fn is None:
        llm_fn = call_llm
    raw = llm_fn(CURIOSITY_PROMPT.format(knowledge_json=json.dumps(knowledge, ensure_ascii=False)))
    questions = raw.get("questions", [])
    # Coerce numeric-like values that some LLMs may return as strings
    for q in questions:
        for key in ("uncertainty", "priority"):
            if key in q:
                val = q[key]
                # Fast path for numeric types
                if isinstance(val, (int, float)):
                    q[key] = float(val)
                    continue
                # Try to coerce numeric strings like '0.8' or '80%'
                try:
                    if isinstance(val, str):
                        s = val.strip()
                        if s.endswith('%'):
                            q[key] = float(s.rstrip('%')) / 100.0
                            continue
                        q[key] = float(s)
                        continue
                except (TypeError, ValueError):
                    pass

                # Map qualitative descriptors to numeric defaults
                if isinstance(val, str):
                    s = val.strip().lower()
                    if 'very high' in s or s == 'high':
                        q[key] = 0.9
                    elif 'high' in s:
                        q[key] = 0.8
                    elif 'medium' in s or 'moderate' in s:
                        q[key] = 0.5
                    elif 'low' in s:
                        q[key] = 0.2
                    else:
                        # Fallback: neutral uncertainty/priority
                        q[key] = 0.5
                else:
                    # Last resort
                    q[key] = 0.5
                # Ensure numeric bounds
                try:
                    q[key] = float(q[key])
                except Exception:
                    q[key] = 0.5
                if q[key] < 0.0:
                    q[key] = 0.0
                if q[key] > 1.0:
                    q[key] = 1.0
        _validate_question(q)
    return questions
