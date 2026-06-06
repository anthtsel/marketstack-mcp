# Operations Guide

How to run, use, and customize the **MarketStack MCP** server from the
terminal. By default it tracks two ETFs — **VTI** (Vanguard Total Stock
Market) and **VOO** (Vanguard S&P 500) — fetches their end-of-day data, and
analyzes them with a local Gemma model via Ollama.

---

## 1. Prerequisites

| Requirement | Notes |
|-------------|-------|
| [`uv`](https://docs.astral.sh/uv/) | Runs the project and manages dependencies. |
| A MarketStack API key | Free tier works. Get one at <https://marketstack.com>. |
| [Ollama](https://ollama.com) | Runs the local AI model used for analysis. |

---

## 2. One-time setup

```bash
# 1. Install dependencies
uv sync

# 2. Create your environment file and add your API key
cp .env.template .env
#    then edit .env and set MARKETSTACK_API_KEY=...

# 3. Pull the local model used for analysis (~3.5 GB)
ollama pull gemma4:e4b
```

Your `.env` is git-ignored, so your API key never gets committed.

---

## 3. Running it

### Option A — run the demo client (easiest)

This drives the server in-process and runs the full VTI/VOO analysis flow:

```bash
uv run client.py
```

You'll see: the configured watchlist → computed 10-day metrics → Gemma's
written analysis comparing the assets → a sample live quote.

### Option B — run the MCP server

Start the server so an MCP-capable client (e.g. Claude Desktop, or your own
client) can connect to it:

```bash
uv run server.py
```

On startup it prints the model, the loaded API key status, and the active
watchlist.

---

## 4. The tools the server exposes

| Tool | What it does |
|------|--------------|
| `get_watchlist` | Lists the assets currently being tracked. |
| `get_watchlist_metrics(days=10)` | Deterministic metrics (net change, range, avg volume, trend) for **every** watchlist asset. |
| `analyze_watchlist(question, days=10)` | **Headline tool** — fetches the watchlist data and has Gemma analyze it. |
| `get_quote(symbol)` | Latest end-of-day quote for any single ticker. |
| `get_eod(symbol, limit=10)` | End-of-day history for any single ticker. |
| `search_tickers(query, limit=5)` | Find ticker symbols by company name / keyword. |
| `ask_gemma(question, context="")` | Ask the local model a question, optionally grounded in data. |
| `analyze_stock(symbol, question, days=5)` | Fetch + analyze a single ticker in one call. |

The metrics are computed in code (not by the AI), so the numbers are exact;
the AI only writes the narrative on top of them.

---

## 5. Adding or modifying tracked assets

The watchlist defaults to `VTI` and `VOO`. You can change it **two** ways.

### Way 1 — no code, via `.env` (quickest)

Set the `WATCHLIST` variable in your `.env` file to a comma-separated list of
symbols. This overrides the default and takes effect on the next run:

```dotenv
# Track the two default ETFs plus the Nasdaq-100 and a bond fund
WATCHLIST=VTI,VOO,QQQ,BND
```

Symbols can be **any ticker MarketStack supports** — ETFs, individual stocks
(`AAPL`, `MSFT`), etc. Not sure of a symbol? Look it up first:

```bash
# Inside the demo client you can call search_tickers, or run the server and
# have your MCP client call:  search_tickers(query="vanguard")
```

### Way 2 — in code, via `DEFAULT_WATCHLIST` (gives each asset a label)

Edit `server.py` and add entries to `DEFAULT_WATCHLIST`. The key is the
symbol; the value is a human-readable description shown in `get_watchlist`:

```python
DEFAULT_WATCHLIST = {
    "VTI": "Vanguard Total Stock Market ETF",
    "VOO": "Vanguard S&P 500 ETF",
    "QQQ": "Invesco Nasdaq-100 ETF",      # <-- added
    "BND": "Vanguard Total Bond Market",  # <-- added
}
```

**Precedence:** if `WATCHLIST` is set in `.env`, it wins and
`DEFAULT_WATCHLIST` is ignored (descriptions are still reused for any symbol
that also appears in `DEFAULT_WATCHLIST`). To go back to the built-in
default, comment out or remove the `WATCHLIST` line in `.env`.

### To remove an asset

Either drop it from the `WATCHLIST` line in `.env`, or delete its line from
`DEFAULT_WATCHLIST` in `server.py`.

---

## 6. Changing the AI model

The analysis model is set by `OLLAMA_MODEL` in `.env` (default `gemma4:e4b`).
It must match a tag from `ollama list` exactly. To use a different local
model:

```bash
ollama pull llama3.1:8b
# then in .env:
#   OLLAMA_MODEL=llama3.1:8b
```

---

## 7. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `MARKETSTACK_API_KEY not set` | You didn't create `.env` or didn't fill in the key. |
| `MarketStack API error [...]` | Bad symbol, exhausted free-tier quota, or invalid key. |
| Analysis hangs or errors on the AI step | Make sure Ollama is running and the model in `OLLAMA_MODEL` is pulled (`ollama list`). |
| Empty / `no data` for a symbol | The free tier is end-of-day only; check the symbol with `search_tickers`. |
