# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "fastmcp",
#   "httpx",
#   "python-dotenv",
#   "ollama",
# ]
# ///
"""
DadCode Episode: MarketStack MCP Server
=======================================
An MCP server that wraps the MarketStack financial API and provides
local AI analysis via Gemma4 running through Ollama.

Setup:
    uv sync                          # install deps from pyproject.toml
    cp .env.template .env            # add your MarketStack API key
    ollama pull gemma4:e4b           # pull the local model (~3.5GB)

Run (no activation needed):
    uv run server.py                 # via pyproject.toml project
    # -- OR standalone, no pyproject.toml needed --
    uv run --script server.py        # uses inline script metadata above
"""

import os
import json
import httpx
import ollama

from dotenv import load_dotenv
from fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()

MARKETSTACK_API_KEY = os.getenv("MARKETSTACK_API_KEY")
MARKETSTACK_BASE_URL = "http://api.marketstack.com/v1"

# The local model name as it appears in `ollama list`
# We use gemma4:e4b — the 4-billion parameter efficient variant of Gemma 4
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e4b")

if not MARKETSTACK_API_KEY:
    raise EnvironmentError(
        "MARKETSTACK_API_KEY not set. Add it to your .env file.\n"
        "Get a free key at: https://marketstack.com"
    )

# ---------------------------------------------------------------------------
# Watchlist — the assets this server tracks and analyzes by default.
#
# To ADD or MODIFY assets, you have two options:
#
#   1. Edit DEFAULT_WATCHLIST below — add a "SYMBOL": "Description" entry.
#      Symbols can be any ticker MarketStack supports: ETFs, stocks, etc.
#
#   2. Override at runtime without touching code, via the WATCHLIST env var
#      in your .env file (comma-separated), e.g.:
#          WATCHLIST=VTI,VOO,QQQ,BND
#      The env var, if set, takes precedence over DEFAULT_WATCHLIST.
#
# See OPERATIONS.md for a full walkthrough.
# ---------------------------------------------------------------------------

DEFAULT_WATCHLIST = {
    "VTI": "Vanguard Total Stock Market ETF",
    "VOO": "Vanguard S&P 500 ETF",
}


def _load_watchlist() -> dict:
    """Build the active watchlist from the WATCHLIST env var, or fall back
    to DEFAULT_WATCHLIST. Returns an ordered {SYMBOL: description} dict."""
    env_value = os.getenv("WATCHLIST", "").strip()
    if not env_value:
        return dict(DEFAULT_WATCHLIST)

    watchlist = {}
    for symbol in env_value.split(","):
        symbol = symbol.strip().upper()
        if symbol:
            # Reuse a known description if we have one, else leave blank.
            watchlist[symbol] = DEFAULT_WATCHLIST.get(symbol, "")
    return watchlist or dict(DEFAULT_WATCHLIST)


WATCHLIST = _load_watchlist()

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP(name="MarketStack MCP")

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _marketstack_get(endpoint: str, params: dict) -> dict:
    """
    Make an authenticated GET request to the MarketStack API.
    Raises on HTTP or API-level errors.
    """
    params["access_key"] = MARKETSTACK_API_KEY

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(f"{MARKETSTACK_BASE_URL}/{endpoint}", params=params)
        response.raise_for_status()
        data = response.json()

    if "error" in data:
        code = data["error"].get("code", "unknown")
        msg  = data["error"].get("message", "No message provided")
        raise RuntimeError(f"MarketStack API error [{code}]: {msg}")

    return data


def _compute_metrics(records: list[dict]) -> dict:
    """
    Compute simple, deterministic analytics from a list of EOD records
    (newest first, as returned by the MarketStack `eod` endpoint).

    This gives real numbers — independent of the LLM — that summarize the
    period: net change, range, average volume, and a coarse trend label.
    """
    closes = [r.get("close") for r in records if r.get("close") is not None]
    if not closes:
        return {"error": "no usable close prices"}

    latest_close   = closes[0]
    oldest_close   = closes[-1]
    change_abs     = latest_close - oldest_close
    change_pct     = (change_abs / oldest_close * 100) if oldest_close else 0.0

    highs   = [r.get("high")   for r in records if r.get("high")   is not None]
    lows    = [r.get("low")    for r in records if r.get("low")    is not None]
    volumes = [r.get("volume") for r in records if r.get("volume") is not None]

    if change_pct > 0.5:
        trend = "up"
    elif change_pct < -0.5:
        trend = "down"
    else:
        trend = "flat"

    return {
        "days":           len(records),
        "latest_close":   round(latest_close, 2),
        "period_change":  round(change_abs, 2),
        "period_change_pct": round(change_pct, 2),
        "period_high":    round(max(highs), 2) if highs else None,
        "period_low":     round(min(lows), 2) if lows else None,
        "avg_volume":     int(sum(volumes) / len(volumes)) if volumes else None,
        "trend":          trend,
    }


# ---------------------------------------------------------------------------
# Tool 1: Latest end-of-day quote (free-tier compatible)
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_quote(symbol: str) -> str:
    """
    Fetch the latest end-of-day quote for a stock ticker symbol.

    Args:
        symbol: Stock ticker, e.g. "AAPL", "MSFT", "TSLA"

    Returns:
        JSON string with the most recent price data.
    """
    data = await _marketstack_get("eod/latest", {"symbols": symbol.upper()})

    if not data.get("data"):
        return json.dumps({"error": f"No intraday data found for symbol: {symbol}"})

    quote = data["data"][0]
    result = {
        "symbol":  quote.get("symbol"),
        "open":    quote.get("open"),
        "high":    quote.get("high"),
        "low":     quote.get("low"),
        "last":    quote.get("last"),
        "close":   quote.get("close"),
        "volume":  quote.get("volume"),
        "date":    quote.get("date"),
        "exchange": quote.get("exchange"),
    }
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# Tool 2: End-of-day historical data
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_eod(symbol: str, limit: int = 10) -> str:
    """
    Fetch end-of-day historical price data for a stock ticker.

    Args:
        symbol: Stock ticker, e.g. "AAPL"
        limit:  Number of trading days to return (default 10, max 100)

    Returns:
        JSON string with a list of daily OHLCV records, newest first.
    """
    limit = max(1, min(limit, 100))  # clamp to safe range
    data  = await _marketstack_get("eod", {"symbols": symbol.upper(), "limit": limit})

    if not data.get("data"):
        return json.dumps({"error": f"No EOD data found for symbol: {symbol}"})

    records = [
        {
            "date":   r.get("date", "")[:10],   # trim to YYYY-MM-DD
            "open":   r.get("open"),
            "high":   r.get("high"),
            "low":    r.get("low"),
            "close":  r.get("close"),
            "volume": r.get("volume"),
        }
        for r in data["data"]
    ]
    return json.dumps({"symbol": symbol.upper(), "records": records}, indent=2)


# ---------------------------------------------------------------------------
# Tool 3: Ticker / exchange search
# ---------------------------------------------------------------------------

@mcp.tool()
async def search_tickers(query: str, limit: int = 5) -> str:
    """
    Search for stock ticker symbols by company name or keyword.

    Args:
        query: Search term, e.g. "Apple", "electric vehicles"
        limit: Number of results to return (default 5)

    Returns:
        JSON string with matching ticker symbols and company names.
    """
    limit = max(1, min(limit, 20))
    data  = await _marketstack_get("tickers", {"search": query, "limit": limit})

    if not data.get("data"):
        return json.dumps({"results": [], "message": f"No tickers found for query: {query}"})

    tickers = [
        {
            "symbol":   t.get("symbol"),
            "name":     t.get("name"),
            "exchange": t.get("stock_exchange", {}).get("acronym"),
            "country":  t.get("stock_exchange", {}).get("country"),
        }
        for t in data["data"]
    ]
    return json.dumps({"query": query, "results": tickers}, indent=2)


# ---------------------------------------------------------------------------
# Tool 4: AI analysis with local Gemma via Ollama
# ---------------------------------------------------------------------------

@mcp.tool()
async def ask_gemma(question: str, context: str = "") -> str:
    """
    Ask the local Gemma4 model a question, optionally with financial context data.

    This is the AI brain of the MCP server. Pass stock data from other tools
    as `context` and ask Gemma to analyze, summarize, or explain it.

    Args:
        question: Natural-language question to ask the model.
        context:  Optional data/context to ground the answer (e.g. raw JSON
                  from get_eod or get_quote). If provided, it is injected into
                  the prompt automatically.

    Returns:
        The model's text response as a string.
    """
    if context.strip():
        prompt = (
            "You are a financial analyst assistant. "
            "Use the following data to answer the question accurately and concisely.\n\n"
            f"=== MARKET DATA ===\n{context}\n\n"
            f"=== QUESTION ===\n{question}"
        )
    else:
        prompt = (
            "You are a financial analyst assistant. "
            f"Answer the following question accurately and concisely:\n\n{question}"
        )

    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )

    return response["message"]["content"]


# ---------------------------------------------------------------------------
# Tool 5: Combo — fetch + analyze in one call
# ---------------------------------------------------------------------------

@mcp.tool()
async def analyze_stock(symbol: str, question: str, days: int = 5) -> str:
    """
    Convenience tool: fetch recent EOD data for a symbol, then ask Gemma
    a question about it — all in one step.

    Args:
        symbol:   Stock ticker, e.g. "AAPL"
        question: What you want to know, e.g. "Is this stock trending up?"
        days:     How many trading days of history to pull (default 5)

    Returns:
        Gemma's analysis as a string.
    """
    # 1. Pull the data
    eod_json = await get_eod(symbol=symbol, limit=days)

    # 2. Ask Gemma about it
    answer = await ask_gemma(question=question, context=eod_json)

    return answer


# ---------------------------------------------------------------------------
# Tool 6: Inspect the configured watchlist
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_watchlist() -> str:
    """
    Return the assets this server is currently tracking.

    The watchlist defaults to VTI and VOO and can be changed via the
    WATCHLIST env var or DEFAULT_WATCHLIST in server.py (see OPERATIONS.md).

    Returns:
        JSON string listing each tracked symbol and its description.
    """
    assets = [
        {"symbol": symbol, "description": desc or None}
        for symbol, desc in WATCHLIST.items()
    ]
    return json.dumps({"count": len(assets), "assets": assets}, indent=2)


# ---------------------------------------------------------------------------
# Tool 7: Fetch + compute metrics for every asset on the watchlist
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_watchlist_metrics(days: int = 10) -> str:
    """
    Fetch recent EOD data for every asset on the watchlist and compute
    deterministic metrics (net change, range, average volume, trend).

    Args:
        days: Number of trading days of history per asset (default 10, max 100).

    Returns:
        JSON string mapping each symbol to its computed metrics.
    """
    days = max(1, min(days, 100))
    results = {}

    for symbol, desc in WATCHLIST.items():
        try:
            data = await _marketstack_get("eod", {"symbols": symbol, "limit": days})
            records = data.get("data", [])
            if not records:
                results[symbol] = {"description": desc or None, "error": "no data"}
                continue
            metrics = _compute_metrics(records)
            metrics["description"] = desc or None
            results[symbol] = metrics
        except Exception as exc:  # surface per-symbol failures, keep going
            results[symbol] = {"description": desc or None, "error": str(exc)}

    return json.dumps({"days": days, "metrics": results}, indent=2)


# ---------------------------------------------------------------------------
# Tool 8: Full watchlist analysis — fetch, compute, then ask Gemma
# ---------------------------------------------------------------------------

@mcp.tool()
async def analyze_watchlist(
    question: str = "Summarize how each asset is performing and how they compare.",
    days: int = 10,
) -> str:
    """
    The headline tool: pull recent data + metrics for the whole watchlist
    (VTI and VOO by default), then have local Gemma analyze them together.

    Args:
        question: What you want to know about the watchlist. Defaults to a
                  general performance comparison.
        days:     Trading days of history per asset (default 10).

    Returns:
        Gemma's analysis of the watchlist as a string.
    """
    metrics_json = await get_watchlist_metrics(days=days)
    return await ask_gemma(question=question, context=metrics_json)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    watch = ", ".join(WATCHLIST.keys())
    print("🚀 Starting MarketStack MCP Server")
    print(f"   Model     : {OLLAMA_MODEL} (via Ollama)")
    print(f"   API       : MarketStack (key loaded ✓)")
    print(f"   Watchlist : {watch}")
    print(
        "   Tools     : get_quote, get_eod, search_tickers, ask_gemma, "
        "analyze_stock,\n"
        "               get_watchlist, get_watchlist_metrics, analyze_watchlist\n"
    )
    mcp.run()


if __name__ == "__main__":
    main()