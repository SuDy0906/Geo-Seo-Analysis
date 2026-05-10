"""
Broad sitemap crawl · stores HTML per site origin for offline scoring.
"""

from __future__ import annotations

import io
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fxstreet_scraper import discover_urls_for_scrape  # noqa: E402
from generic_sitemap import crawl_sitemap_urls  # noqa: E402
from seo_audit import DEFAULT_HEADERS, SITEMAP_ALL_URL  # noqa: E402
from scraper_store import (  # noqa: E402
    SiteStore,
    clear_store,
    fetch_and_store_url,
    hostname_allowed_for_store,
    init_store,
    site_store_from_main_url,
    store_stats,
)

st.set_page_config(page_title="Sitemap crawler", page_icon="🌐", layout="wide")
st.title("Sitemap crawler")
st.caption("Collects every discoverable URL via sitemaps, ideal for sitewide benchmarking before deep editorial runs.")

origin = st.text_input(
    "Site origin",
    value="https://www.fxstreet.com/",
    help="Homepage used to pick the persistent cache folder on disk.",
    key="site_scraper_origin",
)
store = site_store_from_main_url(origin)
init_store(store)

if st.session_state.get("_site_scraper_host") != store.canonical_root_host:
    st.session_state["site_scraper_queue"] = []
st.session_state["_site_scraper_host"] = store.canonical_root_host

stats = store_stats(store)

m1, m2, m3 = st.columns(3)
m1.metric("Hostname", store.canonical_root_host)
m2.metric("Indexed URLs", stats["rows"])
m3.metric("Pages with bodies", stats["ok_bodies"])

sess = requests.Session()
sess.headers.update(DEFAULT_HEADERS)


def _probe_sitemap(seed: str, *, timeout: float = 35.0) -> tuple[int | None, str]:
    """Return (HTTP status or None on transport error, short diagnostic text)."""
    try:
        r = sess.get(seed.strip(), timeout=timeout)
        body = (r.text or "")[:400].replace("\n", " ")
        suf = "…" if len(r.text or "") > 400 else ""
        return r.status_code, f"{body}{suf}"
    except requests.RequestException as exc:
        return None, str(exc)[:520]


def _cloudflare_challenge(diag: str) -> bool:
    d = diag.lower()
    return "just a moment" in d or "cf-browser-verification" in d or "/cdn-cgi/" in d


def _bulk_url_lines(paste: str | None, file_bytes: bytes | None, file_name: str) -> list[str]:
    """Turn textarea + optional upload into stripped URL-ish lines (CSV first column if .csv)."""
    lines_out: list[str] = []

    paste = (paste or "").strip()
    if paste:
        lines_out.extend([ln.strip() for ln in paste.replace("\r\n", "\n").split("\n") if ln.strip()])

    if file_bytes:
        decoded = file_bytes.decode("utf-8", errors="replace").strip()
        if file_name.lower().endswith(".csv"):
            df = pd.read_csv(io.BytesIO(file_bytes))
            if len(df.columns):
                lines_out.extend(s.strip() for s in df.iloc[:, 0].dropna().astype(str) if s.strip())
        elif decoded:
            # Plain text: newline‑separated URLs
            lines_out.extend([ln.strip() for ln in decoded.splitlines() if ln.strip()])

    return lines_out


def _manual_url_queue(lines: list[str], *, store_site: SiteStore) -> tuple[list[str], list[str]]:
    accepted: list[str] = []
    rejected: list[str] = []
    seen: set[str] = set()
    for line in lines:
        u = line.strip().strip('"').strip("'")
        if not u.startswith("http"):
            continue
        host = urlparse(u).hostname or ""
        if hostname_allowed_for_store(host, store_site):
            if u not in seen:
                seen.add(u)
                accepted.append(u)
        else:
            rejected.append(u)
    return accepted, rejected

if store.is_fxstreet:
    st.caption(
        "FXStreet merges national sitemap-all coverage with supplemental editorial feeds whenever available."
    )
    c1, c2 = st.columns(2)
    with c1:
        max_pages = st.number_input("Maximum sitemap discoveries", 500, 80000, 15000, 500, key="ss_fx_mp")
    with c2:
        max_fetches = st.number_input("Maximum XML fetches", 20, 900, 420, 10, key="ss_fx_mf")

    pause = st.slider("Pause between successes (seconds)", 0.0, 2.0, 0.25, 0.05, key="ss_fx_pause")
    max_network = st.number_input("Maximum HTML downloads this session", 5, 20000, 200, 5, key="ss_fx_net")
    skip_ok = st.checkbox("Skip URLs already archived", value=True, key="ss_fx_skip")

    if st.button("Discover sitewide queue", key="ss_fx_disc"):
        with st.spinner("Traversing sitemaps…"):
            urls = discover_urls_for_scrape(
                "full_site",
                session=sess,
                max_sitemap_pages=int(max_pages),
                max_sitemap_fetches=int(max_fetches),
                merge_article_sitemaps_into_full=True,
                timeout=40.0,
            )
        st.session_state["site_scraper_queue"] = urls
        st.success(f"Queued **{len(urls)}** destinations.")
        if not urls:
            code, diag = _probe_sitemap(SITEMAP_ALL_URL, timeout=35.0)
            if code == 200:
                st.warning(
                    "Discovery returned zero URLs although the seed sitemap responded **200**. "
                    "Try raising **Maximum XML fetches**, or inspect whether the response XML uses "
                    "unexpected namespaces or redirects."
                )
            elif code is not None:
                if _cloudflare_challenge(diag):
                    st.error(
                        "**Cloudflare challenge** — the response looks like the interstitial page "
                        '("Just a moment…"), not the real sitemap XML. Datacenter IPs '
                        "(Streamlit Cloud included) are often forced through this check; "
                        "plain `requests` cannot pass it. "
                        "Use **Manual URL queue** below with a list you built on your laptop or exported from a browser session."
                    )
                else:
                    st.warning(
                        f"Sitemap probe **HTTP {code}**. The host may block cloud datacenter egress or require different auth.\n\n"
                        f"_Probe snippet:_ {diag[:280]}"
                    )
            else:
                st.warning(
                    "Could not reach the FXStreet sitemap over the network (transport error).\n\n"
                    f"_Detail:_ {diag}"
                )
else:
    st.caption("Provide any discoverable XML index reachable from your host.")
    sm = st.text_input(
        "Sitemap seed URL",
        value=urljoin(store.seed_url, "sitemap.xml"),
        key="ss_gen_sm",
    )
    c1, c2 = st.columns(2)
    with c1:
        max_pages = st.number_input("Maximum page discoveries", 100, 100_000, 5000, 100, key="ss_gen_mp")
    with c2:
        max_fetches = st.number_input("Maximum XML fetches", 5, 500, 80, 5, key="ss_gen_mf")
    pause = st.slider("Pause between successes (seconds)", 0.0, 2.0, 0.25, 0.05, key="ss_gen_pause")
    max_network = st.number_input("Maximum HTML downloads this session", 5, 20000, 200, 5, key="ss_gen_net")
    skip_ok = st.checkbox("Skip URLs already archived", value=True, key="ss_gen_skip")

    if st.button("Discover crawl queue", key="ss_gen_disc"):
        with st.spinner("Crawling sitemap tree…"):
            urls = crawl_sitemap_urls(
                sm,
                store=store,
                max_page_urls=int(max_pages),
                max_sitemap_fetches=int(max_fetches),
                session=sess,
                timeout=40.0,
            )
        st.session_state["site_scraper_queue"] = urls
        st.success(f"Queued **{len(urls)}** destinations.")
        if not urls:
            seed = (sm or "").strip()
            if seed.startswith("http"):
                code, diag = _probe_sitemap(seed)
                if code is None:
                    st.warning(
                        "Could not reach your sitemap seed (transport error). "
                        "Cloud hosting often differs from local DNS/firewall routing.\n\n"
                        f"_Detail:_ {diag}"
                    )
                elif code >= 400:
                    if _cloudflare_challenge(diag):
                        st.error(
                            "**Cloudflare challenge** on the sitemap seed — see **Manual URL queue** below for a workaround."
                        )
                    else:
                        st.warning(
                            f"Seed sitemap responded **HTTP {code}**. Check URL, HTTPS, "
                            "and whether the remote site allows bots from hosted platforms.\n\n"
                            f"_Probe snippet:_ {diag[:280]}"
                        )

st.divider()
with st.expander("Manual URL queue (when sitemaps are blocked e.g. Cloudflare)", expanded=False):
    st.markdown(
        "Paste **https://…** URLs for this site origin, one per line. "
        "You can build the list on your **laptop** (where sitemap discovery works), from a CMS export, "
        "or copy from browser devtools — then archive here on Cloud."
    )
    manual_txt = st.text_area("URLs (one per line)", height=140, key="ss_manual_lines", label_visibility="collapsed")
    upl = st.file_uploader("Optional: append from `.txt` or `.csv` (first column cell per row)", type=["txt", "csv"], key="ss_manual_file")
    if st.button("Replace queue with pasted / file URLs", key="ss_manual_replace"):
        fn = (upl.name or "urls.txt").lower() if upl is not None else "urls.txt"
        raw_lines = _bulk_url_lines(manual_txt, upl.getvalue() if upl is not None else None, fn)
        good, bad = _manual_url_queue(raw_lines, store_site=store)
        st.session_state["site_scraper_queue"] = good
        if good:
            st.success(f"Queued **{len(good)}** URLs (host allowed for «{store.canonical_root_host}»).")
        else:
            st.warning("No valid URLs for this origin — check each line starts with `https://` and matches the site host.")
        if bad:
            st.caption(f"Dropped **{len(bad)}** URLs (wrong host for this store).")

urls = st.session_state.get("site_scraper_queue") or []

if urls:
    st.write(f"Pending queue · **{len(urls)}** URLs · capped at **{max_network}** fresh downloads.")

    if st.button("Archive queue to disk", type="primary", key="ss_fetch"):
        prog = st.progress(0)
        status = st.empty()
        net = 0
        last_err: list[dict[str, object]] = []
        for i, u in enumerate(urls):
            if net >= int(max_network):
                break
            status.caption(f"Downloading {i + 1} of {len(urls)} targets")
            fr = fetch_and_store_url(u, store=store, session=sess, timeout=28.0, skip_if_ok=skip_ok)
            if fr.skipped:
                prog.progress(min(1.0, (i + 1) / max(len(urls), 1)))
                continue
            net += 1
            if fr.error or (fr.status_code or 499) >= 400:
                last_err.append(
                    {"destination": u[:512], "http_status": fr.status_code, "message": (fr.error or "")[:280]}
                )
            prog.progress(min(1.0, net / max(int(max_network), 1)))
            if pause > 0:
                time.sleep(pause)

        prog.empty()
        status.empty()
        st.session_state["site_scraper_last_errors"] = last_err[:500]
        st.success("Session capture complete.")
        st.rerun()

errs = st.session_state.get("site_scraper_last_errors") or []
if errs:
    st.subheader("Capture exceptions")
    st.dataframe(
        pd.DataFrame(errs).rename(
            columns={"destination": "URL", "http_status": "HTTP status", "message": "Message"}
        ),
        use_container_width=True,
        height=200,
        hide_index=True,
    )

with st.expander("Clear local cache for this origin", expanded=False):
    if st.button("Erase stored HTML for this hostname", key="ss_wipe"):
        clear_store(store)
        st.session_state.pop("site_scraper_queue", None)
        st.success("Workspace cleared.")
        st.rerun()

st.divider()
st.markdown(
    f"**Artifact path:** `{store.data_dir.relative_to(ROOT)}` — pair with **Article index** when you "
    "need prioritized editorial subsets. Offline studios never refetch HTML."
)
