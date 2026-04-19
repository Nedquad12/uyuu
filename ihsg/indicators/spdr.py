"""
indicators/spdr.py — SPDR Holdings Trend

Bandingkan Grand Total terbaru vs sebelumnya untuk satu ticker.

Logika:
  latest > previous  →  +1  (SPDR beli / tambah)
  latest < previous  →  -1  (SPDR jual / kurangi)
  latest == previous →   0  (tidak berubah)
  tidak ada data     →   0

Data di-cache saat startup / reload.
"""

import logging
import os
import glob
import pandas as pd
from datetime import datetime

logger = logging.getLogger(__name__)


# ── Public: skor dari cache ────────────────────────────────────────────────────

def score_spdr(ticker: str, spdr_cache: dict) -> int:
    """
    Hitung skor SPDR berdasarkan cache.

    Args:
        ticker     : kode saham, e.g. "BBCA"
        spdr_cache : dict {ticker: {"latest_qty": float, "prev_qty": float}}

    Returns:
        +1  SPDR beli / tambah
        -1  SPDR jual / kurangi
         0  tidak ada data / tidak berubah
    """
    entry = spdr_cache.get(ticker.upper())
    if entry is None:
        return 0

    latest = entry.get("latest_qty", 0.0)
    prev   = entry.get("prev_qty",   0.0)

    if latest == prev:
        return 0
    return 1 if latest > prev else -1


def get_spdr_detail(ticker: str, spdr_cache: dict) -> dict:
    """Return detail untuk debugging / laporan."""
    entry = spdr_cache.get(ticker.upper(), {})
    latest = entry.get("latest_qty", 0.0)
    prev   = entry.get("prev_qty",   0.0)
    return {
        "latest_qty":  latest,
        "prev_qty":    prev,
        "latest_date": entry.get("latest_date", "-"),
        "prev_date":   entry.get("prev_date",   "-"),
        "score":       score_spdr(ticker, spdr_cache),
    }


# ── Builder: dipanggil saat startup / reload ──────────────────────────────────

def build_spdr_cache(spdr_folder: str) -> dict:
    """
    Baca semua file Excel SPDR, bangun cache per ticker.
    Kolom qty: 'Grand Total' (berbeda dari BlackRock yang pakai 'Quantity Total').

    Struktur cache:
        {
          "BBCA": {
              "latest_qty":  1_000_000.0,
              "prev_qty":      900_000.0,
              "latest_date": "2025-03-10",
              "prev_date":   "2025-02-10",
          },
          ...
        }

    Args:
        spdr_folder : path ke folder berisi ddmmyy.xlsx SPDR

    Returns:
        dict cache (kosong jika folder / file tidak ditemukan)
    """
    cache: dict = {}

    if not os.path.exists(spdr_folder):
        logger.warning(f"[SPDR] Folder tidak ditemukan: {spdr_folder}")
        return cache

    excel_files = sorted(
        glob.glob(os.path.join(spdr_folder, "*.xlsx")) +
        glob.glob(os.path.join(spdr_folder, "*.xls"))
    )

    if not excel_files:
        logger.warning("[SPDR] Tidak ada file Excel di SPDR folder.")
        return cache

    dataframes = []
    for fp in excel_files:
        try:
            filename = os.path.basename(fp)
            date_str = filename.split(".")[0]
            if len(date_str) != 6:
                continue
            day   = int(date_str[0:2])
            month = int(date_str[2:4])
            year  = 2000 + int(date_str[4:6])
            file_date = datetime(year, month, day)

            df = pd.read_excel(fp)
            df["Date"] = file_date
            dataframes.append(df)
        except Exception as e:
            logger.warning(f"[SPDR] Gagal baca {fp}: {e}")
            continue

    if not dataframes:
        logger.warning("[SPDR] Semua file gagal dibaca.")
        return cache

    combined = pd.concat(dataframes, ignore_index=True)

    if "Ticker" not in combined.columns:
        logger.error("[SPDR] Kolom 'Ticker' tidak ditemukan.")
        return cache

    combined["Ticker"] = combined["Ticker"].astype(str).str.strip().str.upper()
    combined = combined[~combined["Ticker"].isin(["", "NAN", "NONE"])]

    qty_col = "Grand Total"
    if qty_col not in combined.columns:
        logger.error(f"[SPDR] Kolom '{qty_col}' tidak ditemukan.")
        return cache

    combined[qty_col] = pd.to_numeric(combined[qty_col], errors="coerce").fillna(0)

    for ticker, grp in combined.groupby("Ticker"):
        daily = (
            grp.groupby("Date")[qty_col]
            .sum()
            .sort_index()
        )

        if len(daily) < 2:
            continue

        cache[ticker] = {
            "latest_qty":  float(daily.iloc[-1]),
            "prev_qty":    float(daily.iloc[-2]),
            "latest_date": daily.index[-1].strftime("%Y-%m-%d"),
            "prev_date":   daily.index[-2].strftime("%Y-%m-%d"),
        }

    logger.info(f"[SPDR] Cache dibangun: {len(cache)} ticker")
    return cache
