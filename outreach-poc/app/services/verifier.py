"""Step 7 - Claim checker.

Deterministic check that a draft only uses what the fact pack allows. It runs on every
draft regardless of which drafter or agent produced it.
"""
from __future__ import annotations

import re

from app.models import Draft, FactPack, Verification

URL_RX = re.compile(r"https?://[^\s)>\]]+")
# amounts ($25,000), percentages (5.2%), thousands (25,000), decimals (5.2)
# share-class ids (P101I), document ids (D104), CRM ids (ACT105), fact ids (F-DOC-D101), signal ids
INTERNAL_ID_RX = re.compile(r"\b(?:P\d{3}[A-Z]|D\d{3}|ACT\d{3,}|F-[A-Z]+(?:-[A-Z0-9]+)*|SIG-[A-Z0-9-]+)\b")
NUM_RX = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?|\b\d+(?:\.\d+)?\s?%|\b\d{1,3}(?:,\d{3})+\b|\b\d+\.\d+\b")


def _norm(token: str) -> str:
    return re.sub(r"[\s$,%]", "", token).rstrip(".")


def verify(draft: Draft, pack: FactPack, catalog_names: list[str]) -> Verification:
    text = f"{draft.subject}\n{draft.body}"
    low = text.lower()
    included = pack.included_facts()
    issues, warnings, checked = [], [], 0

    allowed_urls = {f.url for f in included if f.url}
    for url in URL_RX.findall(text):
        checked += 1
        if url.rstrip(".,") not in allowed_urls:
            issues.append(f"Link not in approved material: {url}")
    for f in included:
        if f.url and f.url not in text:
            warnings.append(f"Selected material not linked in the body: {f.label}")

    allowed_nums = {_norm(v) for f in included for v in f.values if v}
    allowed_nums |= {_norm(n) for f in included for n in NUM_RX.findall(f.statement)}
    for tok in NUM_RX.findall(text):
        checked += 1
        if _norm(tok) not in allowed_nums:
            issues.append(f"Figure not supported by the fact pack: {tok.strip()}")

    allowed_names = {v.lower() for f in included for v in f.values if v}
    for name in catalog_names:
        if name.lower() in low:
            checked += 1
            if name.lower() not in allowed_names:
                issues.append(f"Mentions a fund not in the fact pack: {name}")

    no_urls = URL_RX.sub(" ", text)
    leaked = sorted(set(INTERNAL_ID_RX.findall(no_urls)))
    if leaked:
        issues.append(f"Internal identifiers visible to the advisor: {', '.join(leaked)}")

    for term in pack.banned_terms:
        if re.search(rf"\b{re.escape(term)}\b", low):
            issues.append(f"Uses an excluded signal: '{term}'")

    for f in included:
        if f.kind == "performance" and f.disclosure:
            checked += 1
            if f.disclosure[:40].lower() not in low:
                issues.append("Performance figures quoted without the required disclosure.")

    words = len(draft.body.split())
    if words > pack.tone.max_words + 40:
        warnings.append(f"Longer than the {pack.tone.style} target ({words} words, target ~{pack.tone.max_words}).")
    return Verification(passed=not issues, checked=checked, issues=issues, warnings=warnings)
