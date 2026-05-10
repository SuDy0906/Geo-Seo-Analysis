# Geo · SEO Intelligence

Streamlit workspaces for FXStreet‑oriented **Foundation SEO**, **Citation / GEO‑style readiness**, **Performance link** (joined metrics), plus **sitemap crawl** and **article index** against a local HTML cache (`data/`; not committed).

**Repository:** [github.com/SuDy0906/Geo-Seo-Analysis](https://github.com/SuDy0906/Geo-Seo-Analysis)

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
pip install -r requirements-spacy.txt   # optional: Python 3.11–3.12 recommended for spaCy wheels
copy .streamlit\secrets.toml.example .streamlit\secrets.toml   # optional; add ANTHROPIC_API_KEY
python -m streamlit run "GEO_&_SEO_Analysis.py"
```

Citation scoring works **without** spaCy (`en_core_web_sm`); spaCy adds a small entity-based adjustment when the model is installed.

## Deploy on Streamlit Community Cloud

1. Fork or connect **[SuDy0906/Geo-Seo-Analysis](https://github.com/SuDy0906/Geo-Seo-Analysis)** in [Streamlit Community Cloud](https://streamlit.io/cloud).
2. **Main file path:** `GEO_&_SEO_Analysis.py` (quotes not needed in the UI).
3. **Python:** `runtime.txt` should select **3.11.x** — in the dashboard, ensure you are **not** forcing a prerelease interpreter (for example **3.14**) that Streamlit ignores `runtime.txt` for; if builds still use 3.14, see Troubleshooting below.
4. **Dependencies:** Cloud installs **`requirements.txt` only** (no spaCy). That avoids **`blis` wheel / compile failures** on Python versions spaCy doesn’t publish wheels for yet. For entity-aware spaCy scoring on Cloud you’d need a **custom Dockerfile** or **pinned 3.11/3.12** plus merging `requirements-spacy.txt` into a single file after confirming wheels install.
5. **Optional secrets:** Claude‑assisted dimensions in **Citation readiness** → add `ANTHROPIC_API_KEY` under **App settings → Secrets** (see [.streamlit/secrets.toml.example](.streamlit/secrets.toml.example)).
6. Scrape **`data/`** is empty on deploy; use **Sitemap crawler** / **Article index** inside the app to populate cache (persistent only if Cloud storage mounted; ephemeral otherwise).

## Troubleshooting installs (`blis`, `ERROR: Failed building wheel`)

**Cause:** **[spaCy](https://spacy.io)** depends on **`blis`** (C extension). On **Python 3.14** (and some other combos) there is often **no pre-built wheel** for `blis`, so `pip` compiles from source and can fail unless you have full build tools—or the build is broken on that Python.

**What to do**

- Prefer **Python 3.11 or 3.12** for installs that include **`requirements-spacy.txt`** (venv, Docker, or Streamlit runtime).
- Deploy with **`requirements.txt` only** (current default): the app installs without spaCy and citation logic still runs; you only skip the spaCy refinement.
- Never commit API keys into the repo—use Streamlit **Secrets**.
