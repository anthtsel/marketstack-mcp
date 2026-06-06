# MarketStack MCP

An [MCP](https://modelcontextprotocol.io) server that wraps the
[MarketStack](https://marketstack.com) financial API and analyzes a watchlist
of assets using a **local** Gemma model via [Ollama](https://ollama.com) — no
data leaves your machine for the analysis step.

By default it tracks two ETFs:

- **VTI** — Vanguard Total Stock Market
- **VOO** — Vanguard S&P 500

It fetches their end-of-day data, computes exact metrics (net change, range,
average volume, trend), and lets the local model write the narrative on top.

## Features

- 📈 **Watchlist tracking** — VTI & VOO out of the box, fully configurable
- 🔢 **Deterministic metrics** — computed in code, not guessed by the model
- 🤖 **Local AI analysis** — Gemma via Ollama, so your queries stay private
- 🧰 **MCP tools** for quotes, EOD history, ticker search, and ad-hoc analysis

## Quick start

```bash
uv sync                       # install dependencies
cp .env.template .env         # then add your MarketStack API key
ollama pull gemma4:e4b        # pull the local model (~3.5 GB)

uv run client.py              # run the VTI/VOO demo
# or
uv run server.py              # start the MCP server for an MCP client
```

You'll need [`uv`](https://docs.astral.sh/uv/), a free
[MarketStack API key](https://marketstack.com), and
[Ollama](https://ollama.com).

## Tools

| Tool | What it does |
|------|--------------|
| `get_watchlist` | Lists the tracked assets. |
| `get_watchlist_metrics(days=10)` | Computed metrics for every watchlist asset. |
| `analyze_watchlist(question, days=10)` | Fetches the watchlist and has Gemma analyze it. |
| `get_quote(symbol)` | Latest end-of-day quote for any ticker. |
| `get_eod(symbol, limit=10)` | End-of-day history for any ticker. |
| `search_tickers(query, limit=5)` | Find ticker symbols by name/keyword. |
| `ask_gemma(question, context="")` | Ask the local model, optionally grounded in data. |
| `analyze_stock(symbol, question, days=5)` | Fetch + analyze a single ticker. |

## Customizing the watchlist

Track different assets without touching code by setting `WATCHLIST` in `.env`:

```dotenv
WATCHLIST=VTI,VOO,QQQ,BND
```

Or edit `DEFAULT_WATCHLIST` in `server.py` to add labelled entries. See
**[OPERATIONS.md](OPERATIONS.md)** for the full walkthrough, including the
model swap and troubleshooting.

## Documentation

- **[OPERATIONS.md](OPERATIONS.md)** — full guide: setup, running, adding/
  modifying assets, changing the AI model, and troubleshooting.

## License

No license specified yet — add one if you intend others to reuse this.
