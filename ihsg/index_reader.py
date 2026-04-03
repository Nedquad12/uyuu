"""
index_reader.py — Konversi file Excel indeks harian ke JSON

Format file  : ddmmyy.xlsx di /home/ec2-user/database/index
Kolom utama  : Kode Indeks, Sebelumnya, Tertinggi, Terendah, Penutupan,
               Volume, Nilai, Frekuensi, Selisih, Kapitalisasi Pasar*

Output JSON per file: ddmmyy.json di /home/ec2-user/database/injson
Struktur JSON:
  [
    {
      "date":        "2025-11-03",
      "code":        "COMPOSITE",
      "prev":        8163.875,
      "high":        8200.0,
      "low":         8100.0,
      "close":       8180.0,
      "change":      16.125,
      "volume":      12345678,
      "value":       15870554576191,
      "frequency":   2091906,
      "mkt_cap":     15049765382032300
    },
    ...
  ]
"""

import json
import logging
import os
from datetime import datetime

import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

INDEX_DIR  = "/home/ec2-user/database/index"
INJSON_DIR = "/home/ec2-user/database/injson"

# Mapping kolom XLSX → key JSON
COL_MAP = {
    "Kode Indeks":        "code",
    "Sebelumnya":         "prev",
    "Tertinggi":          "high",
    "Terendah":           "low",
    "Penutupan":          "close",
    "Selisih":            "change",
    "Volume":             "volume",
    "Nilai":              "value",
    "Frekuensi":          "frequency",
    "Kapitalisasi Pasar*": "mkt_cap",
}

NUMERIC_COLS = ["prev", "high", "low", "close", "change",
                "volume", "value", "frequency", "mkt_cap"]


def _parse_date_from_filename(filename: str) -> datetime | None:
    """ddmmyy.xlsx → datetime. None jika gagal."""
    try:
        base = filename.replace(".xlsx", "").replace(".xls", "")
        if len(base) == 6:
            d = int(base[:2])
            m = int(base[2:4])
            y = 2000 + int(base[4:6])
            return datetime(y, m, d)
    except ValueError as e:
        logger.warning(f"Cannot parse date from {filename}: {e}")
    return None


def get_index_files(directory: str = INDEX_DIR) -> list[dict]:
    """Return list file Excel di directory, sorted ascending by date."""
    files = []
    for fn in os.listdir(directory):
        if not fn.endswith((".xlsx", ".xls")):
            continue
        dt = _parse_date_from_filename(fn)
        if dt:
            files.append({
                "filename": fn,
                "date":     dt,
                "path":     os.path.join(directory, fn),
            })
    files.sort(key=lambda x: x["date"])
    return files


def read_index_excel(file_path: str, file_date: datetime) -> list[dict] | None:
    """
    Baca satu file Excel indeks, return list of record dict.
    Setiap record = satu baris (satu kode indeks) untuk hari itu.
    """
    try:
        df = pd.read_excel(file_path, header=0)

        if "Kode Indeks" not in df.columns:
            logger.error(f"Kolom 'Kode Indeks' tidak ditemukan di {file_path}")
            return None

        # Rename kolom sesuai mapping
        df = df.rename(columns=COL_MAP)
        df = df.dropna(subset=["code"])
        df["code"] = df["code"].astype(str).str.strip().str.upper()

        # Numerik
        for col in NUMERIC_COLS:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        date_str = file_date.strftime("%Y-%m-%d")

        records = []
        for _, row in df.iterrows():
            rec = {"date": date_str}
            for std_col in ["code"] + NUMERIC_COLS:
                if std_col in df.columns:
                    val = row[std_col]
                    # Pastikan JSON-serialisable
                    if hasattr(val, "item"):   # numpy scalar
                        val = val.item()
                    rec[std_col] = val
            records.append(rec)

        logger.info(f"Berhasil baca {len(records)} indeks dari {file_path}")
        return records

    except Exception as e:
        logger.error(f"Error membaca {file_path}: {e}")
        return None


def index_excel_to_json(file_info: dict, output_dir: str = INJSON_DIR) -> str | None:
    """
    Konversi satu file Excel indeks ke JSON.
    Return path file JSON, atau None jika gagal.
    """
    os.makedirs(output_dir, exist_ok=True)

    records = read_index_excel(file_info["path"], file_info["date"])
    if records is None:
        return None

    date_str  = file_info["date"].strftime("%d%m%y")
    json_path = os.path.join(output_dir, f"{date_str}.json")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    logger.info(f"Saved {len(records)} records → {json_path}")
    return json_path


def convert_all_index_files(
    index_dir: str = INDEX_DIR,
    injson_dir: str = INJSON_DIR,
) -> tuple[int, int, list[str]]:
    """
    Konversi semua file Excel di index_dir ke JSON di injson_dir.

    Returns:
        (success_count, total_count, error_filenames)
    """
    os.makedirs(injson_dir, exist_ok=True)
    files = get_index_files(index_dir)

    if not files:
        logger.warning(f"Tidak ada file Excel di {index_dir}")
        return 0, 0, []

    success, errors = 0, []
    for fi in files:
        result = index_excel_to_json(fi, injson_dir)
        if result:
            success += 1
        else:
            errors.append(fi["filename"])

    return success, len(files), errors
