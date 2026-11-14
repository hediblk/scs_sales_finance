"""AI text on top of computed facts: triage note and email draft.

Rules:
- Code decides every number, every flag and the triage recommendation. The model only writes wording.
- Every number in the model's text must already appear in the facts we sent; otherwise the template text is used.
- No key, a timeout, an error or a refusal: the template text is used. The app never waits more than ~20 s.
"""
import os
import re
from pathlib import Path

MODEL = "claude-opus-5-5"
ROOT = Path(__file__).resolve().parents[1]


def _load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            k, sep, v = line.partition("=")
            if sep and k.strip() and not k.strip().startswith("#"):
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()
_client = None


def enabled():
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def _get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic(timeout=20.0, max_retries=1)
    return _client


_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text):
    return {n.replace(",", "").rstrip(".").lstrip("0") or "0" for n in _NUM.findall(text)}


def numbers_ok(text, facts_text):
    """True when every number the model wrote is one we gave it (small counting words like 1-12 allowed)."""
    allowed = _numbers(facts_text)
    for n in _numbers(text):
        try:
            if float(n) <= 12:
                continue
        except ValueError:
            pass
        if n not in allowed:
            return False
    return True


def _call(system, prompt, max_tokens=700, effort="low"):
    import anthropic
    client = _get_client()
    try:
        resp = client.beta.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": effort},
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
    except (anthropic.APIConnectionError, anthropic.APITimeoutError, anthropic.RateLimitError,
            anthropic.APIStatusError, TypeError) as e:
        return None, f"ai_error: {type(e).__name__}"
    if resp.stop_reason == "refusal":
        return None, "ai_refused"
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
    if resp.stop_reason == "max_tokens":
        return (text or None), "ai_truncated"  # cut off: callers must not use it as finished text
    return (text or None), "ai"


SYSTEM = ("You write short, plain business text for Chrome & Oak Office Supply staff. "
          "Use only the facts given. Never compute, round or invent a number: copy numbers exactly as written in the facts. "
          "No greetings beyond one line, no sign-off slogans, no dashes as punctuation.")


def write(kind, facts_text, fallback, max_tokens=700, system=None, effort="low"):
    """kind: 'draft' (first line subject, blank line, body) or 'triage' (two lines: summary, why).
    Returns (text, source) where source is 'ai' or the reason the template was used."""
    if not enabled():
        return fallback, "template: no ANTHROPIC_API_KEY"
    if kind == "draft":
        task = ("Write the email. First line: the subject only. Then a blank line. Then the body, under 140 words, "
                "addressed to the recipient named in the facts.")
    elif kind == "answer":
        task = ("Answer the question in at most two sentences, using only the query result above. "
                "If the result does not answer the question, say so. Copy numbers exactly as they appear in the result.")
    else:
        task = ("Write two lines. Line 1: a one-sentence summary of the case. "
                "Line 2: one sentence on why a person should or need not review it, consistent with the decision in the facts.")
    text, source = _call(system or SYSTEM, f"Facts:\n{facts_text}\n\n{task}", max_tokens, effort)
    if not text or source != "ai":
        return fallback, f"template: {source}"
    if not numbers_ok(text, facts_text):
        return fallback, "template: AI text had a number not in the facts"
    return text, source
