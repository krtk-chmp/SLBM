#!/usr/bin/env python3
"""Backfill index F&O history (NIFTY, BANKNIFTY, FINNIFTY, ...).

Tiny table — about 5 rows per trading day — so 5 years costs almost nothing.
Handles both NSE file formats (old pre-Jul-2024, UDIFF after).

Usage: python backfill_index.py 1830
"""
import io
import sys
import zipfile
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from slbm import db, ingest
from slbm.nse import NSEClient

logging.basicConfig(level=logging.WARNING)
DB_PATH = Path(__file__).parent / "data" / "slbm.db"
ARCH = "https://nsearchives.nseindia.com"


def fo_urls(d: date) -> list[str]:
    udiff = f"{ARCH}/content/fo/BhavCopy_NSE_FO_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
    old = (f"{ARCH}/content/historical/DERIVATIVES/{d.year}/"
           f"{d.strftime('%b').upper()}/fo{d.strftime('%d%b%Y').upper()}bhav.csv.zip")
    return [udiff, old] if d >= date(2024, 7, 1) else [old, udiff]


def fetch(args):
    nse, d = args
    for u in fo_urls(d):
        b = nse._get(u, tries=2)
        if b and b[:2] == b"PK":
            try:
                z = zipfile.ZipFile(io.BytesIO(b))
                return d, z.read(z.namelist()[0]).decode("utf-8", "replace")
            except Exception:
                pass
    return d, None


def main(days: int):
    con = db.connect(DB_PATH)
    have = {r[0] for r in con.execute("SELECT DISTINCT date FROM index_fo")}
    todo = []
    d = date.today() - timedelta(days=days)
    while d <= date.today():
        if d.weekday() < 5 and d.isoformat() not in have:
            todo.append(d)
        d += timedelta(days=1)
    print(f"{len(todo)} days to fetch", flush=True)

    clients = [NSEClient() for _ in range(3)]
    jobs = [(clients[i % 3], dd) for i, dd in enumerate(todo)]
    done = 0
    with ThreadPoolExecutor(max_workers=3) as ex:
        for d, txt in ex.map(fetch, jobs):
            if txt:
                ingest.store_index_fo(con, d, txt)
            done += 1
            if done % 100 == 0:
                print(f"{done}/{len(todo)}", flush=True)
    print("index backfill complete", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1830)
