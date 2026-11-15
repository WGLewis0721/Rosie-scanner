"""Optional local Model Context Protocol adapter for Rosie's on-demand research.

Install: pip install 'mcp>=1.28,<2'
Launch: python rosie_mcp.py
Uses stdio only; no HTTP listener, scheduler, account or order execution.
"""
from mcp.server.fastmcp import FastMCP
from rosie_advisor import run_nba, resolved_market_audit, read_history, fit_calibrator

mcp = FastMCP("Rosie Read-Only Research")

@mcp.tool()
def nba_opportunities(date: str = "", bankroll: float = 0.0,
                      history_file: str = "data/nba_history.csv",
                      sportsbooks_file: str = "") -> dict:
    """Research NBA pregame moneyline markets on demand; return sourced REVIEW/PASS, not orders.

    date: YYYYMMDD (empty = current date in US Central).
    bankroll: optional USD reference for conservative conditional stake caps.
    history_file: local historical CSV from explicit 'history' CLI call.
    sportsbooks_file: optional other pregame bookmaker quotes CSV.
    """
    return run_nba(date or None, history_file, sportsbooks_file or None,
                   max(0.,min(float(bankroll),1000000.)))

@mcp.tool()
def nba_calibration_status(history_file: str = "data/nba_history.csv") -> dict:
    """Show historical sample size, held-out Brier/log loss, and model gate."""
    return fit_calibrator(read_history(history_file))

@mcp.tool()
def nba_resolved_catalog(limit: int = 100) -> dict:
    """Read settled Kalshi and closed Polymarket catalog counts; no trading."""
    return resolved_market_audit(limit)

if __name__ == "__main__":
    mcp.run(transport="stdio")
