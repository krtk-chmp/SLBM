#!/usr/bin/env python3
"""Trim the database so it stays comfortably under GitHub's 100 MB file limit.

What is kept and why:
  slb_trades      ALL      the 5-year lending history — seasonality, fee charts, scores
  index_fo        ALL      index view (tiny)
  participant_oi  ALL      FII/DII flows (tiny)
  prices          2 years  backtest forward-returns + current yield
  futures         2 years  cost of carry + backtest
  fo_options      2 years  put-call trend (chart shows 180 days) + backtest
  fo_strikes      10 days  "where the bets sit" chart only needs the latest day
  slb_openpos     90 days  signals compare the last week
  scores          30 days  only the newest day is displayed

Everything trimmed here can be re-downloaded from NSE with backfill_fo.py /
backfill_index.py if it is ever needed again. The irreplaceable part — the
5 years of SLBM lending fees — is never touched.

Usage: python prune_db.py
"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "slbm.db"

# table -> days of history to keep (None = keep everything)
POLICY = {
    "prices": 730,
    "futures": 730,
    "fo_options": 730,
    "fo_strikes": 10,
    "slb_openpos": 90,
    "scores": 30,
}


def size_mb(path: Path) -> float:
    return path.stat().st_size / 1048576


def prune(con: sqlite3.Connection, verbose: bool = True) -> int:
    total = 0
    for table, days in POLICY.items():
        try:
            newest = con.execute(f"SELECT MAX(date) FROM {table}").fetchone()[0]
        except sqlite3.OperationalError:
            continue  # table not created yet
        if not newest:
            continue
        cutoff = con.execute("SELECT date(?, ?)", (newest, f"-{days} days")).fetchone()[0]
        n = con.execute(f"DELETE FROM {table} WHERE date < ?", (cutoff,)).rowcount
        total += n
        if verbose and n:
            print(f"  {table:16} removed {n:>8,} rows older than {cutoff}")
    con.commit()
    return total


def main():
    if not DB_PATH.exists():
        print(f"No database at {DB_PATH}")
        return 1
    before = size_mb(DB_PATH)
    con = sqlite3.connect(DB_PATH)
    print(f"Database before: {before:.1f} MB")
    removed = prune(con)
    print(f"Removed {removed:,} rows. Reclaiming space...")
    con.execute("VACUUM")
    con.close()
    after = size_mb(DB_PATH)
    print(f"Database after:  {after:.1f} MB  (saved {before - after:.1f} MB)")
    if after > 90:
        print("WARNING: still close to GitHub's 100 MB limit — tighten POLICY further.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
