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
DadCode Episode: MarketStack MCP Client
=======================================
A test client that drives the MarketStack MCP server in-process,
demonstrating all five tools including local Gemma4 AI analysis
via Ollama running gemma4:e4b.

Run (no activation needed):
    uv run client.py
"""

import asyncio
import json
from fastmcp import Client


SERVER_SCRIPT = "server.py"   # path to server.py (same directory)


async def run_demo():
    # Connect to the server in-process (no network needed for local testing)
    async with Client(SERVER_SCRIPT) as client:

        print("=" * 60)
        print("  DadCode: MarketStack MCP + Gemma4 Demo")
        print("=" * 60)

        # -------------------------------------------------------
        # 1. List available tools
        # -------------------------------------------------------
        tools = await client.list_tools()
        print(f"\n📦 Available tools ({len(tools)}):")
        for t in tools:
            print(f"   • {t.name}: {t.description[:60]}...")

        # -------------------------------------------------------
        # 2. Search for a ticker
        # -------------------------------------------------------
        print("\n" + "-" * 60)
        print("🔍 Searching tickers for 'Apple'...")
        result = await client.call_tool("search_tickers", {"query": "Apple", "limit": 3})
        data = json.loads(result.content[0].text)
        print(json.dumps(data, indent=2))

        # -------------------------------------------------------
        # 3. Get a live quote
        # -------------------------------------------------------
        print("\n" + "-" * 60)
        print("📈 Fetching latest quote for AAPL...")
        result = await client.call_tool("get_quote", {"symbol": "AAPL"})
        quote  = json.loads(result.content[0].text)
        print(json.dumps(quote, indent=2))

        # -------------------------------------------------------
        # 4. Get EOD history
        # -------------------------------------------------------
        print("\n" + "-" * 60)
        print("📊 Fetching last 7 days of EOD data for MSFT...")
        result  = await client.call_tool("get_eod", {"symbol": "MSFT", "limit": 7})
        eod_raw = result.content[0].text                 # keep raw for Gemma context
        eod     = json.loads(eod_raw)
        for r in eod["records"]:
            print(f"   {r['date']}  close=${r['close']:.2f}  vol={r['volume']:,}")

        # -------------------------------------------------------
        # 5. Ask Gemma about the EOD data
        # -------------------------------------------------------
        print("\n" + "-" * 60)
        print("🤖 Asking Gemma4 to analyze the MSFT data...")
        result = await client.call_tool(
            "ask_gemma",
            {
                "question": (
                    "Based on the last 7 trading days, is MSFT showing bullish or "
                    "bearish momentum? Summarize the key price action in 3-4 sentences."
                ),
                "context": eod_raw,
            },
        )
        print("\nGemma says:")
        print(result.content[0].text)

        # -------------------------------------------------------
        # 6. One-shot combo: analyze_stock
        # -------------------------------------------------------
        print("\n" + "-" * 60)
        print("⚡ One-shot analyze_stock: TSLA, last 5 days...")
        result = await client.call_tool(
            "analyze_stock",
            {
                "symbol":   "TSLA",
                "question": (
                    "What was the price range this week and does the volume suggest "
                    "institutional interest? Keep it brief."
                ),
                "days": 5,
            },
        )
        print("\nGemma on TSLA:")
        print(result.content[0].text)

        # -------------------------------------------------------
        # 7. Free-form financial question (no market data context)
        # -------------------------------------------------------
        print("\n" + "-" * 60)
        print("💬 Asking Gemma a general financial question...")
        result = await client.call_tool(
            "ask_gemma",
            {
                "question": (
                    "What is the difference between end-of-day stock data and "
                    "intraday data, and when would a retail investor use each?"
                ),
            },
        )
        print("\nGemma explains:")
        print(result.content[0].text)

        print("\n" + "=" * 60)
        print("  ✅ Demo complete!")
        print("=" * 60)


def main():
    asyncio.run(run_demo())


if __name__ == "__main__":
    main()