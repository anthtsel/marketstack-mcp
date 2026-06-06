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
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("🚀 Starting MarketStack MCP Server")
    print(f"   Model : {OLLAMA_MODEL} (via Ollama)")
    print(f"   API   : MarketStack (key loaded ✓)")
    print(f"   Tools : get_quote, get_eod, search_tickers, ask_gemma, analyze_stock\n")
    mcp.run()


if __name__ == "__main__":
    main()