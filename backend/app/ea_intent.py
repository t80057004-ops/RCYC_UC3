from __future__ import annotations
import re
from difflib import get_close_matches

_FUZZY_VOCAB = ["ambassador", "ambassadors", "authority", "supervisor", "representative", "escalate", "escalation"]
_TOKEN = re.compile(r"[a-z0-9']+")

def _normalize(text: str) -> str:
    out = []
    for tok in _TOKEN.findall(text.lower()):
        if len(tok) >= 8 and tok not in _FUZZY_VOCAB:
            match = get_close_matches(tok, _FUZZY_VOCAB, n=1, cutoff=0.85)
            if match:
                tok = match[0]
        out.append(tok)
    return " ".join(out)

_PATTERNS = [
    r"\bambassadors?\b", r"\bsupervisor\b", r"\bmanager\b", r"\bmanagement\b",
    r"\bescalat(e|ion)\b", r"\brepresentative\b", r"\bhumans?\b",
    r"\bhigher (authority|up|ups|management)\b",
    r"\b(senior|someone senior|person in charge|someone in charge|in charge)\b",
    r"\b(real|live|actual) (person|agent|human|people)\b",
    r"\b(speak|talk|chat|connect|transfer|put me through|pass me|reach) (me )?(to|with) (a |an |the |your )?(person|someone|somebody|agent|rep|staff|team|colleague|member of staff)\b",
    r"\b(call|phone|ring|contact) me\b", r"\bcall ?back\b", r"\bcomplain to\b",
]
_COMPILED = [re.compile(p) for p in _PATTERNS]
_NEGATION_BEFORE = re.compile(r"\b(no|not|never|without|dont|don't|do not|doesnt|doesn't|isnt|isn't)\b(\s+\S+){0,3}\s*$")

def wants_human(message: str) -> bool:
    text = _normalize(message)
    for pattern in _COMPILED:
        for m in pattern.finditer(text):
            if not _NEGATION_BEFORE.search(text[: m.start()]):
                return True
    return False

def has_keyword(message: str, keywords: list[str]) -> bool:
    """Word-boundary prefix match: 'issue' matches 'issues' but not 'tissue'."""
    lowered = message.lower()
    return any(re.search(r"\b" + re.escape(kw), lowered) for kw in keywords)
