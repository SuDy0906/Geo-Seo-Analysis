# Geo · SEO Intelligence

Streamlit workspaces for FXStreet‑oriented **Foundation SEO**, **Citation / GEO‑style readiness**, **Performance link** (joined metrics), plus **sitemap crawl** and **article index** against a local HTML cache (`data/`; not committed).

**Repository:** [github.com/SuDy0906/Geo-Seo-Analysis](https://github.com/SuDy0906/Geo-Seo-Analysis)

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
python -m spacy download en_core_web_sm
copy .streamlit\secrets.toml.example .streamlit\secrets.toml   # optional; add ANTHROPIC_API_KEY
python -m streamlit run "GEO_&_SEO_Analysis.py"
```

## Deploy on Streamlit Community Cloud

1. Fork or connect **[SuDy0906/Geo-Seo-Analysis](https://github.com/SuDy0906/Geo-Seo-Analysis)** in [Streamlit Community Cloud](https://streamlit.io/cloud).
2. **Main file path:** `GEO_&_SEO_Analysis.py` (quotes not needed in the UI).
3. **Python:** `runtime.txt` pins **3.11.9**.
4. **Dependencies:** `requirements.txt` installs **spaCy** and the **`en_core_web_sm`** wheel so entity‑aware citation scoring runs in the cloud.
5. **Optional secrets:** enable Claude‑assisted dimensions in **Citation readiness** → add `ANTHROPIC_API_KEY` under **App settings → Secrets** (same layout as [.streamlit/secrets.toml.example](.streamlit/secrets.toml.example)).
6. Scrape **`data/`** is empty on deploy; use **Sitemap crawler** / **Article index** inside the app to populate cache (persistent only if Cloud storage mounted; ephemeral otherwise).
