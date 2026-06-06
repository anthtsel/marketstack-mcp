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
demonstrating the watchlist analysis (VTI + VOO by default) plus the
underlying tools, including local Gemma4 AI analysis via Ollama
running gemma4:e4b.

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
        # 2. Show the configured watchlist (VTI, VOO by default)
        # -------------------------------------------------------
        print("\n" + "-" * 60)
        print("⭐ Configured watchlist:")
        result = await client.call_tool("get_watchlist", {})
        watch  = json.loads(result.content[0].text)
        for asset in watch["assets"]:
            print(f"   • {asset['symbol']:<6} {asset.get('description') or ''}")

        # -------------------------------------------------------
        # 3. Deterministic metrics for the whole watchlist
        # -------------------------------------------------------
        print("\n" + "-" * 60)
        print("📊 Computing 10-day metrics for the watchlist...")
        result  = await client.call_tool("get_watchlist_metrics", {"days": 10})
        metrics = json.loads(result.content[0].text)["metrics"]
        for symbol, m in metrics.items():
            if "error" in m:
                print(f"   {symbol}: ⚠️  {m['error']}")
                continue
            print(
                f"   {symbol:<6} close=${m['latest_close']:<9} "
                f"chg={m['period_change_pct']:+.2f}%  trend={m['trend']}  "
                f"avg_vol={m['avg_volume']:,}"
            )

        # -------------------------------------------------------
        # 4. Headline: let Gemma analyze the watchlist
        # -------------------------------------------------------
        print("\n" + "-" * 60)
        print("🤖 Asking Gemma to analyze VTI vs VOO...")
        result = await client.call_tool(
            "analyze_watchlist",
            {
                "question": (
                    "Compare the two ETFs over the last 10 trading days. Which has "
                    "stronger momentum, how do they differ, and what does that say "
                    "about the broad market? Keep it to 4-5 sentences."
                ),
                "days": 10,
            },
        )
        print("\nGemma on the watchlist:")
        print(result.content[0].text)

        # -------------------------------------------------------
        # 5. Underlying tools still work for any single symbol
        # -------------------------------------------------------
        print("\n" + "-" * 60)
        print("📈 Fetching latest quote for VOO...")
        result = await client.call_tool("get_quote", {"symbol": "VOO"})
        print(json.dumps(json.loads(result.content[0].text), indent=2))

        print("\n" + "=" * 60)
        print("  ✅ Demo complete!")
        print("=" * 60)


def main():
    asyncio.run(run_demo())


if __name__ == "__main__":
    main()