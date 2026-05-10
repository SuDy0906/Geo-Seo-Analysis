"""
FXStreet citation-readiness scoring · shared by the Streamlit Citation readiness studio.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import requests
import trafilatura
from bs4 import BeautifulSoup

from http_session import make_fetch_session
from seo_audit import attach_default_headers, validate_fxstreet_url, _host_ok_for_fxstreet

_HOST_OK = _host_ok_for_fxstreet

_CLAUDE_MODEL_DEFAULT = os.environ.get("CITEABILITY_CLAUDE_MODEL", "claude-sonnet-4-20250514")


@dataclass
class CiteabilityReport:
    url: str
    final_url: str
    status_code: int | None
    error: str | None
    word_count: int
    dimensions: dict[str, float]
    total: float
    suggestions: list[str] = field(default_factory=list)
    excerpt: str = ""
    used_spacy: bool = False
    used_textstat: bool = False
    used_claude: bool = False
    claude_error: str | None = None


def report_to_row(rep: CiteabilityReport) -> dict[str, Any]:
    row: dict[str, Any] = {
        "url": rep.url,
        "final_url": rep.final_url,
        "status_code": rep.status_code,
        "error": rep.error or "",
        "citeability_total": rep.total,
        "word_count": rep.word_count,
        "used_spacy": rep.used_spacy,
        "used_textstat": rep.used_textstat,
        "used_claude": rep.used_claude,
        "claude_error": rep.claude_error or "",
    }
    for k, v in rep.dimensions.items():
        row[f"dim_{k}"] = v
    return row


def _word_count(s: str) -> int:
    return len(re.findall(r"\b[\w']+\b", s))


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _extract_visible_html(html: str) -> tuple[str, str]:
    txt = (
        trafilatura.extract(html, include_comments=False, include_tables=True, favor_recall=True)
        or ""
    )
    if len(txt.strip()) < 80:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        txt = soup.get_text(" ", strip=True)
    excerpt = (txt[:560] + "…") if len(txt) > 560 else txt
    return txt, excerpt


def _regex_dimensions(text: str) -> dict[str, float]:
    n_words = max(_word_count(text), 1)
    nums = len(re.findall(r"\b\d+(?:,\d{3})*(?:\.\d+)?\b", text))
    pct = len(re.findall(r"%", text))
    currency = len(re.findall(r"\b(?:USD|EUR|GBP|JPY|\$)\b|\$[\d,]+", text, re.I))
    dates = len(re.findall(r"\b\d{4}-\d{2}-\d{2}\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2}", text, re.I))
    questions = len(re.findall(r"\?", text))
    bullets = len(re.findall(r"(?m)^\s*[\*\-•]", text))

    density = _clip(nums / max(n_words / 180.0, 1e-6) * 12.0 + pct * 2.5 + currency * 3.5)
    spec = _clip(nums * 2.8 + pct * 4 + currency * 3)
    freshness = _clip(dates * 14 + nums * 0.15)

    headings = "\n".join(line for line in text.splitlines() if line.strip())[:12000].count("\n")

    readability = _clip(48.0 + (3000 / max(n_words, 1)) * 25)
    scannability = _clip(bullets * 6 + min(headings * 8, 40) + 12)

    auth = _clip(nums * 0.5 + pct * 1.8 + currency * 1.8 + 35)
    time_signal = _clip(dates * 22 + pct * 1.8 + currency * 1.8 + 20)
    cite_ev = _clip(nums * 1.8 + currency * 3.2 + pct * 2.2 + 18)
    answer = _clip(45 + max(0, 12 - questions) * 2.2 + density * 0.15)
    unique = _clip(38 + min(n_words / 120.0, 40) + density * 0.12)

    return {
        "specificity": spec,
        "data_density": density,
        "authority_framing": auth,
        "freshness_signals": freshness,
        "timeliness": time_signal,
        "readability": readability,
        "scannability": scannability,
        "citation_evidence": cite_ev,
        "answer_shape": answer,
        "uniqueness": unique,
    }


def _spacy_adjust(text: str, dims: dict[str, float]) -> tuple[dict[str, float], bool]:
    try:
        import spacy

        nlp = spacy.load("en_core_web_sm")
    except Exception:
        return dims, False

    doc = nlp(text[:50_000])
    ents = len(doc.ents)
    money = sum(1 for e in doc.ents if e.label_ in ("MONEY", "QUANTITY"))
    dates = sum(1 for e in doc.ents if e.label_ == "DATE")
    out = dict(dims)
    out["authority_framing"] = _clip(out["authority_framing"] + min(ents * 0.8, 18))
    out["citation_evidence"] = _clip(out["citation_evidence"] + money * 3.5 + dates * 2.5)
    out["specificity"] = _clip(out["specificity"] + money * 2.2)
    return out, True


def _textstat_readability(text: str, dims: dict[str, float]) -> tuple[dict[str, float], bool]:
    try:
        import textstat
    except Exception:
        return dims, False

    out = dict(dims)
    try:
        fk = float(textstat.flesch_reading_ease(text))
    except Exception:
        fk = 40.0
    out["readability"] = _clip(fk)
    return out, True


def _claude_scores(
    *,
    text: str,
    url: str,
    api_key: str,
    model: str,
) -> tuple[dict[str, float] | None, str | None]:
    try:
        from anthropic import Anthropic
    except Exception as e:
        return None, str(e)

    sample = text[:12_000]
    prompt = (
        "Score this article excerpt for answer_shape and uniqueness for AI citation quality. "
        "Return ONLY JSON: {\"answer_shape\":0-100,\"uniqueness\":0-100}.\n\n"
        f"URL: {url}\n\n---\n{sample}"
    )
    try:
        client = Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=model,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = (msg.content[0].text or "").strip()
        m = re.search(r"\{[^}]+\}", raw, re.S)
        if not m:
            return None, "Claude did not return JSON"
        data = json.loads(m.group())
        a = float(data.get("answer_shape", 0))
        u = float(data.get("uniqueness", 0))
        return {"answer_shape": _clip(a), "uniqueness": _clip(u)}, None
    except Exception as e:
        return None, str(e)


def score_fxstreet_citeability(
    url: str,
    timeout: float = 25.0,
    session: requests.Session | None = None,
    *,
    prefetched_html: str | None = None,
    prefetched_final_url: str | None = None,
    prefetched_status_code: int | None = None,
    use_spacy: bool = True,
    use_textstat: bool = True,
    use_claude: bool = False,
    anthropic_api_key: str | None = None,
    claude_model: str = _CLAUDE_MODEL_DEFAULT,
) -> CiteabilityReport:
    pre = validate_fxstreet_url(url)
    if pre:
        return CiteabilityReport(
            url=url.strip(),
            final_url=url.strip(),
            status_code=None,
            error=pre,
            word_count=0,
            dimensions={},
            total=0.0,
        )

    key = (anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    do_claude = bool(use_claude and key)

    sess = session or make_fetch_session()
    attach_default_headers(sess)

    http_status: int
    final: str
    html: str

    if prefetched_html is not None:
        final = (prefetched_final_url or url).strip()
        if not _HOST_OK(urlparse(final).hostname or ""):
            return CiteabilityReport(
                url=url.strip(),
                final_url=final,
                status_code=prefetched_status_code or 200,
                error="Cached final URL is outside fxstreet.com.",
                word_count=0,
                dimensions={},
                total=0.0,
            )
        http_status = prefetched_status_code if prefetched_status_code is not None else 200
        if http_status >= 400:
            return CiteabilityReport(
                url=url.strip(),
                final_url=final,
                status_code=http_status,
                error=f"HTTP {http_status}",
                word_count=0,
                dimensions={},
                total=0.0,
            )
        html = prefetched_html
    else:
        try:
            resp = sess.get(url.strip(), timeout=timeout, allow_redirects=True)
        except Exception as e:
            return CiteabilityReport(
                url=url.strip(),
                final_url=url.strip(),
                status_code=None,
                error=str(e),
                word_count=0,
                dimensions={},
                total=0.0,
            )

        final = resp.url
        if validate_fxstreet_url(final):
            return CiteabilityReport(
                url=url.strip(),
                final_url=final,
                status_code=resp.status_code,
                error="Redirect left fxstreet.com.",
                word_count=0,
                dimensions={},
                total=0.0,
            )
        if resp.status_code >= 400:
            return CiteabilityReport(
                url=url.strip(),
                final_url=final,
                status_code=resp.status_code,
                error=f"HTTP {resp.status_code}",
                word_count=0,
                dimensions={},
                total=0.0,
            )
        html = resp.text
        http_status = resp.status_code

    text, excerpt = _extract_visible_html(html)
    wc = _word_count(text)
    if wc < 40:
        return CiteabilityReport(
            url=url.strip(),
            final_url=final,
            status_code=http_status,
            error="Too little extractable article text.",
            word_count=wc,
            dimensions={},
            total=0.0,
            excerpt=excerpt,
        )

    dims = _regex_dimensions(text)
    used_spacy = False
    if use_spacy:
        dims, used_spacy = _spacy_adjust(text, dims)
    used_txt = False
    if use_textstat:
        dims, used_txt = _textstat_readability(text, dims)

    claude_err: str | None = None
    used_cl = False
    if do_claude:
        adj, claude_err = _claude_scores(text=text, url=final, api_key=key, model=claude_model)
        if adj:
            dims["answer_shape"] = adj["answer_shape"]
            dims["uniqueness"] = adj["uniqueness"]
            used_cl = True

    total = _clip(sum(dims.values()) / max(len(dims), 1))

    suggestions: list[str] = []
    if dims.get("readability", 70) < 45:
        suggestions.append("Tighten sentences and reduce jargon to improve readability.")
    if dims.get("citation_evidence", 50) < 40:
        suggestions.append("Add explicit figures, dates, or sources LLMs can quote.")
    if dims.get("answer_shape", 50) < 45:
        suggestions.append("Open with a direct answer (what / where / when) before context.")

    return CiteabilityReport(
        url=url.strip(),
        final_url=final,
        status_code=http_status,
        error=None,
        word_count=wc,
        dimensions=dims,
        total=total,
        suggestions=suggestions,
        excerpt=excerpt,
        used_spacy=used_spacy,
        used_textstat=used_txt,
        used_claude=used_cl,
        claude_error=claude_err,
    )
