# FINN: Only what matters.

A mobile-first financial agent for a 20-stock Indian equity portfolio (NSE/BSE). Foundation, Push and Pull are built: data sources, SQLite store, API, web app, ranked digest, alerts and results cards.

## Run it (one command)

Needs Python 3.11+ and Node 18+.

    pip install -r requirements.txt
    cp .env.example .env        # optional: add ANTHROPIC_API_KEY (needed from the Push stage on)
    python start.py             # open http://localhost:3000

First run tries live data. If sources are unreachable it loads **labelled sample data** and shows a banner.

## Check live sources on your machine

    python -m backend.cli verify-sources    # probes Yahoo, NSE, BSE, screener.in once each
    python -m backend.cli verify-tickers    # all 25 tickers return prices
    python -m backend.cli refresh           # prices + announcements + document links
    python -m backend.cli sample --force    # synthetic data for demos/tests
    python -m pytest -q tests

## Layout

- `config/` portfolio (20 tickers, weights), ad hoc list (5), settings (thresholds, models, schedules)
- `backend/sources/` Yahoo, NSE, BSE, screener.in fetchers (fetch + normalise only)
- `backend/pipeline/` ingest, sample data, refresh. `backend/metrics.py` return, volume ratio, z-score
- `backend/api/` FastAPI. `web/` Next.js 14 + Tailwind, light theme, 4 tabs

## Status and honesty notes

- Built in an environment where Yahoo/NSE/BSE/screener.in were unreachable. Fetch code follows those sites'
  APIs as known, but is **unverified against the live sites**; run `verify-sources` first.
  Parser tests use hand-written fixtures, labelled as approximations.
- BSE scrip codes in the config were filled from memory; `verify-sources` / manual check recommended.
- Without an API key the LLM layer runs in mock mode (Push/Pull stages).

## Push stage (what is in it)

- `backend/push/classify.py` 17 categories by rules; only unplaceable filings go to the cheap model
- `backend/push/score.py` S = base + severity + market reaction + position; tiers 70/40 (config)
- `backend/push/calc.py` results maths in code (EBITDA, QoQ/YoY, margin bps, bank NII/PPOP, validation)
- `backend/push/enrich.py` PDF statement pages -> cheap model -> card; one-liners for other categories
- `backend/push/alerts.py` price (z-score or fixed %), volume, filing, confirmed; one engine for live and backtest preview
- `backend/push/digest.py` windowed digest, weekend fallback, summary line, briefing
- `python -m backend.cli process` re-runs classify/score/enrich/alerts

Not built yet: browser push notifications, voice, real Ask answers (Pull). Results extraction from real PDFs is
untested (no live filings were reachable); in sample mode, figures are synthetic and labelled as such.

## Pull stage (what is in it)

- `backend/pull/financials.py` + `snapshot.py` screener.in tables -> six tiles, trajectory, growing/compressing/cash callouts (no model)
- `backend/pull/docs.py` annual report + last 4 transcripts -> pages -> chunks with stable ids (`T-Q2FY26-p7-c3`)
- `backend/pull/retrieval.py` BM25 + cue filters (no vector DB)
- `backend/pull/promises.py` extract -> normalise -> verify quote -> find actual -> score -> delivery rate -> flags -> verdict
- `backend/pull/bullbear.py` three bull and three bear points; points citing ids outside the packet are rejected and re-asked once
- `backend/pull/ask.py` cited answers; uncited sentences dropped; "Not found in the company's documents." when unsupported
- `backend/pull/research.py` + `runner.py` the research job, streamed over SSE, cached by document hash
- `python -m backend.cli research SUZLON` runs one company from the terminal

Without ANTHROPIC_API_KEY the model steps use rule-based fallbacks and the UI says so ("written by rules").
Not built: streaming of chat answers (they arrive whole), OCR for scanned PDFs, IR-page fallback.
Parsers for screener.in markup and real PDFs are unverified against the live site.
