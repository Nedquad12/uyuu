import os
import pandas as pd
import json
from excel_reader import read_excel_data, get_excel_files

CACHE_DIR = "/home/ec2-user/database/cache"

def ensure_cache_dir():
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

def cache_path(file_path: str) -> str:
    filename = os.path.basename(file_path)
    return os.path.join(CACHE_DIR, filename.replace(".xlsx", ".txt").replace(".xls", ".txt"))

def load_from_cache(file_path: str):
    path = cache_path(file_path)
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return pd.DataFrame(data)
        except Exception as e:
            print(f"[CACHE] Gagal load cache {path}: {e}")
    return None

def save_to_cache(file_path: str, df: pd.DataFrame):
    ensure_cache_dir()
    path = cache_path(file_path)
    try:
        with open(path, "w") as f:
            json.dump(df.to_dict(orient="list"), f)
        print(f"[CACHE] Cache tersimpan: {path}")
    except Exception as e:
        print(f"[CACHE] Gagal simpan cache {path}: {e}")

def read_or_cache(file_path: str):
    df = load_from_cache(file_path)
    if df is not None:
        return df
    df = read_excel_data(file_path)
    if df is not None:
        save_to_cache(file_path, df)
    return df

def clear_cache():
    if os.path.exists(CACHE_DIR):
        for f in os.listdir(CACHE_DIR):
            try:
                os.remove(os.path.join(CACHE_DIR, f))
            except:
                pass
        print("[CACHE] Semua cache dihapus.")

def preload_cache():
    """Baca semua file Excel dan simpan ke cache"""
    ensure_cache_dir()
    directory = "/home/ec2-user/database/wl"
    excel_files = get_excel_files(directory)
    for file_info in excel_files:
        file_path = file_info['path']
        if load_from_cache(file_path) is None:  # belum ada cache
            print(f"[CACHE] Preloading {file_path}")
            df = read_excel_data(file_path)
            if df is not None:
                save_to_cache(file_path, df)
    print("[CACHE] Preload selesai ✅")
