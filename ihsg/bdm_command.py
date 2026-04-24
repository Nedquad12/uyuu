"""
bdm_command.py
==============
Handler /bdm untuk broker summary dari neobdm.tech.
Output: gambar horizontal bar chart (buy vs sell per broker).

Usage di Telegram:
    /bdm BBCA                         → 5 hari terakhir, val_all
    /bdm BBCA 10Apr2025 16Apr2025     → rentang custom
    /bdm BBCA net                     → mode net buy/sell
    /bdm BBCA foreign                 → filter foreign only

Endpoint API (via api_server.py):
    GET /api/broker/{ticker}?start=10+Apr+2025&end=16+Apr+2025&mode=val&fda=A&top=20
"""

import os
import sys
import io
import logging
import asyncio
import tempfile
from datetime import datetime, timedelta
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode

from admin.auth import is_authorized_user, is_vip_user
from neobdm import NeoBDM, _fmt_date

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

TOP_N        = 20          # berapa broker ditampilkan
DEFAULT_DAYS = 5           # default rentang hari ke belakang

# Warna chart
COLOR_BUY    = "#26a65b"   # hijau
COLOR_SELL   = "#e74c3c"   # merah
COLOR_BG     = "#1a1a2e"   # dark navy background
COLOR_TEXT   = "#e0e0e0"   # teks terang
COLOR_GRID   = "#2d2d4e"   # grid subtle
COLOR_ACCENT = "#f39c12"   # kuning untuk judul

# ── Singleton session neobdm ───────────────────────────────────────────────────
_neo: Optional[NeoBDM] = None

def _get_neo() -> NeoBDM:
    """Return NeoBDM instance (login sekali, reuse session)."""
    global _neo
    if _neo is None or not _neo._logged_in:
        _neo = NeoBDM()
        _neo.login()
        logger.info("[BDM] Login ke neobdm.tech berhasil")
    return _neo


def _relogin() -> NeoBDM:
    """Force re-login (kalau session expired)."""
    global _neo
    _neo = NeoBDM()
    _neo.login()
    logger.info("[BDM] Re-login ke neobdm.tech berhasil")
    return _neo


# ── Auth ──────────────────────────────────────────────────────────────────────

def _is_allowed(uid: int) -> bool:
    return is_authorized_user(uid) or is_vip_user(uid)


# ── Data fetcher ──────────────────────────────────────────────────────────────

def fetch_broker_data(
    ticker: str,
    start_date: str,
    end_date: str,
    mode: str = "val",   # "val" atau "net"
    fda: str  = "A",     # "A" all, "F" foreign, "D" domestic
) -> dict:
    """
    Ambil data broker summary dari neobdm.
    Return dict dari get_broker_summary() atau raise Exception.
    """
    neo = _get_neo()
    try:
        fda_map = {"A": "all", "F": "foreign", "D": "domestic"}
        key = f"{mode.lower()}_{fda_map.get(fda.upper(), 'all')}"
        raw = neo.get_broker_summary(ticker, start_date, end_date)
        return raw
    except PermissionError:
        # Session expired, coba re-login sekali
        neo = _relogin()
        return neo.get_broker_summary(ticker, start_date, end_date)


# ── Chart builder ─────────────────────────────────────────────────────────────

def _parse_lot(s: str) -> float:
    """Parse string lot/val dari neobdm ke float. Contoh: '1.234.567' → 1234567."""
    if not s or s in ("-", ""):
        return 0.0
    try:
        clean = s.strip().lstrip("-").replace(".", "").replace(",", "")
        return float(clean)
    except Exception:
        return 0.0


def _build_broker_map(rows: list) -> dict:
    """
    Dari list rows (buy_broker/sell_broker terpisah), gabungkan jadi dict:
    { broker_code: {"buy": float, "sell": float} }
    """
    broker_map: dict[str, dict] = {}

    for row in rows:
        # BUY side
        b = row.get("buy_broker", "").strip()
        if b and b != "-":
            if b not in broker_map:
                broker_map[b] = {"buy": 0.0, "sell": 0.0}
            broker_map[b]["buy"] += _parse_lot(row.get("buy_lot", "0"))

        # SELL side
        s = row.get("sell_broker", "").strip()
        if s and s != "-":
            if s not in broker_map:
                broker_map[s] = {"buy": 0.0, "sell": 0.0}
            # sell_lot sudah di-prefix "-" di neobdm.py, kita ambil absolut
            broker_map[s]["sell"] += _parse_lot(row.get("sell_lot", "0").lstrip("-"))

    return broker_map


def build_chart(
    data: dict,
    key: str  = "val_all",
    top_n: int = TOP_N,
) -> bytes:
    """
    Build horizontal bar chart buy vs sell per broker.

    Args:
        data  : hasil get_broker_summary()
        key   : "val_all", "val_foreign", "val_domestic",
                "net_all", "net_foreign", "net_domestic"
        top_n : jumlah broker teratas yang ditampilkan

    Returns:
        PNG bytes
    """
    rows = data.get(key, [])
    if not rows:
        raise ValueError(f"Tidak ada data untuk key '{key}'")

    ticker     = data.get("ticker", "?")
    start_date = data.get("start_date", "")
    end_date   = data.get("end_date", "")

    broker_map = _build_broker_map(rows)

    # Hitung total (buy + sell) per broker untuk sorting
    totals = {
        b: v["buy"] + v["sell"]
        for b, v in broker_map.items()
    }

    # Ambil top_n broker by total volume
    top_brokers = sorted(totals, key=lambda x: totals[x], reverse=True)[:top_n]
    top_brokers = list(reversed(top_brokers))  # balik biar broker terbesar di atas

    buys  = [broker_map[b]["buy"]  for b in top_brokers]
    sells = [broker_map[b]["sell"] for b in top_brokers]

    # Normalisasi ke ribu lot biar angka ga terlalu gede
    scale     = 1_000
    unit_label = "ribu lot"
    max_val = max(max(buys, default=0), max(sells, default=0))
    if max_val == 0:
        raise ValueError("Semua nilai nol, tidak ada data valid.")

    buys_s  = [b / scale for b in buys]
    sells_s = [s / scale for s in sells]

    # ── Plot ──────────────────────────────────────────────────────────────────
    n      = len(top_brokers)
    height = max(6, n * 0.45 + 2.5)
    fig, ax = plt.subplots(figsize=(12, height))
    fig.patch.set_facecolor(COLOR_BG)
    ax.set_facecolor(COLOR_BG)

    y_pos = np.arange(n)
    bar_h = 0.35

    # BUY bars (ke kanan, positif)
    bars_buy = ax.barh(
        y_pos + bar_h / 2, buys_s,
        height=bar_h,
        color=COLOR_BUY,
        alpha=0.88,
        label="Buy",
        zorder=3,
    )

    # SELL bars (ke kiri, negatif)
    bars_sell = ax.barh(
        y_pos - bar_h / 2, [-s for s in sells_s],
        height=bar_h,
        color=COLOR_SELL,
        alpha=0.88,
        label="Sell",
        zorder=3,
    )

    # Label nilai di ujung bar
    for i, (b, s) in enumerate(zip(buys_s, sells_s)):
        if b > 0:
            ax.text(
                b + max_val / scale * 0.01,
                y_pos[i] + bar_h / 2,
                f"{b:,.0f}",
                va="center", ha="left",
                color=COLOR_BUY,
                fontsize=7.5, fontweight="bold",
            )
        if s > 0:
            ax.text(
                -(s + max_val / scale * 0.01),
                y_pos[i] - bar_h / 2,
                f"{s:,.0f}",
                va="center", ha="right",
                color=COLOR_SELL,
                fontsize=7.5, fontweight="bold",
            )

    # Y axis — nama broker
    ax.set_yticks(y_pos)
    ax.set_yticklabels(top_brokers, color=COLOR_TEXT, fontsize=9, fontfamily="monospace")

    # X axis
    ax.tick_params(axis="x", colors=COLOR_TEXT, labelsize=8)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color(COLOR_GRID)

    # Garis tengah (nol)
    ax.axvline(0, color=COLOR_TEXT, linewidth=1.2, alpha=0.5, zorder=2)

    # Grid
    ax.xaxis.grid(True, color=COLOR_GRID, linestyle="--", alpha=0.5, zorder=0)
    ax.set_axisbelow(True)

    # Label sumbu X
    ax.set_xlabel(unit_label, color=COLOR_TEXT, fontsize=9)

    # X label simetris
    xlim = max(max(buys_s, default=1), max(sells_s, default=1)) * 1.25
    ax.set_xlim(-xlim, xlim)

    # X tick label — tampilkan sebagai positif di kedua sisi
    xticks = ax.get_xticks()
    ax.set_xticklabels([f"{abs(t):,.0f}" for t in xticks], color=COLOR_TEXT, fontsize=8)

    # ── Judul ─────────────────────────────────────────────────────────────────
    mode_label = key.replace("_", " ").upper()
    title = f"BROKER SUMMARY — {ticker}  [{mode_label}]"
    subtitle = f"{start_date}  →  {end_date}   |   Top {n} broker by volume"

    ax.set_title(
        f"{title}\n{subtitle}",
        color=COLOR_ACCENT,
        fontsize=11,
        fontweight="bold",
        pad=14,
        loc="left",
    )

    # ── Legend ────────────────────────────────────────────────────────────────
    legend = ax.legend(
        handles=[
            mpatches.Patch(color=COLOR_BUY,  label=f"Buy  ▶"),
            mpatches.Patch(color=COLOR_SELL, label=f"◀  Sell"),
        ],
        loc="lower right",
        facecolor=COLOR_BG,
        edgecolor=COLOR_GRID,
        labelcolor=COLOR_TEXT,
        fontsize=9,
    )

    plt.tight_layout(pad=1.5)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, facecolor=COLOR_BG)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ── Telegram handler ──────────────────────────────────────────────────────────

def _parse_args(args: list[str]) -> tuple[str, str, str, str, str]:
    """
    Parse args dari command /bdm.
    Return (ticker, start_date, end_date, mode, fda)

    Contoh:
        /bdm BBCA                         → default 5 hari, val all
        /bdm BBCA net                     → mode net
        /bdm BBCA foreign                 → fda foreign
        /bdm BBCA 10Apr2025 16Apr2025     → custom range
        /bdm BBCA 10Apr2025 16Apr2025 net foreign
    """
    if not args:
        return "", "", "", "val", "A"

    ticker = args[0].upper()
    mode   = "val"
    fda    = "A"
    start  = ""
    end    = ""

    remaining = args[1:]

    for token in remaining:
        t = token.lower()
        if t in ("net",):
            mode = "net"
        elif t in ("val", "value"):
            mode = "val"
        elif t in ("foreign", "f", "asing"):
            fda = "F"
        elif t in ("domestic", "d", "lokal"):
            fda = "D"
        elif t in ("all", "a"):
            fda = "A"
        else:
            # Coba parse sebagai tanggal — format: 10Apr2025 atau 10 Apr 2025
            try:
                # Normalize format
                clean = token.replace(" ", "")
                for fmt in ("%d%b%Y", "%d%B%Y", "%Y-%m-%d", "%d/%m/%Y"):
                    try:
                        dt = datetime.strptime(clean, fmt)
                        formatted = dt.strftime("%d %b %Y")
                        if not start:
                            start = formatted
                        else:
                            end = formatted
                        break
                    except ValueError:
                        continue
            except Exception:
                pass

    # Default: 5 hari ke belakang dari hari ini
    if not start:
        today = datetime.now()
        start = (today - timedelta(days=DEFAULT_DAYS)).strftime("%d %b %Y")
        end   = today.strftime("%d %b %Y")
    elif start and not end:
        end = datetime.now().strftime("%d %b %Y")

    return ticker, start, end, mode, fda


def _key_from_mode_fda(mode: str, fda: str) -> str:
    fda_map = {"A": "all", "F": "foreign", "D": "domestic"}
    return f"{mode}_{fda_map.get(fda.upper(), 'all')}"


async def cmd_bdm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/bdm TICKER [start] [end] [net/val] [all/foreign/domestic]"""
    uid = update.effective_user.id
    if not _is_allowed(uid):
        await update.message.reply_text("⛔ Kamu tidak punya akses ke fitur ini.")
        return

    args = context.args or []
    if not args:
        await update.message.reply_text(
            "⚠️ Usage:\n"
            "<code>/bdm BBCA</code> — 5 hari terakhir\n"
            "<code>/bdm BBCA net</code> — mode net\n"
            "<code>/bdm BBCA foreign</code> — filter asing\n"
            "<code>/bdm BBCA 10Apr2025 16Apr2025</code> — rentang custom\n"
            "<code>/bdm BBCA 10Apr2025 16Apr2025 net foreign</code> — full custom",
            parse_mode=ParseMode.HTML,
        )
        return

    ticker, start, end, mode, fda = _parse_args(args)
    if not ticker:
        await update.message.reply_text("❌ Ticker tidak valid.")
        return

    key = _key_from_mode_fda(mode, fda)
    fda_label = {"A": "All", "F": "Foreign", "D": "Domestic"}.get(fda, fda)

    msg = await update.message.reply_text(
        f"⏳ Fetching broker summary <b>{ticker}</b> "
        f"({mode.upper()} · {fda_label}) "
        f"<code>{start} → {end}</code> …",
        parse_mode=ParseMode.HTML,
    )

    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None,
            lambda: fetch_broker_data(ticker, start, end, mode, fda),
        )

        img_bytes = await loop.run_in_executor(
            None,
            lambda: build_chart(data, key=key, top_n=TOP_N),
        )

        caption = (
            f"📊 <b>Broker Summary — {ticker}</b>\n"
            f"Mode: <b>{mode.upper()}</b> · Filter: <b>{fda_label}</b>\n"
            f"Periode: <code>{data.get('start_date', start)} → {data.get('end_date', end)}</code>"
        )

        await update.message.reply_photo(
            photo=img_bytes,
            caption=caption,
            parse_mode=ParseMode.HTML,
        )
        await msg.delete()

    except PermissionError as e:
        await msg.edit_text(f"❌ Login neobdm gagal: {e}")
    except ValueError as e:
        await msg.edit_text(f"⚠️ {e}")
    except Exception as e:
        logger.exception("[BDM] Error fetch/chart: %s", e)
        await msg.edit_text(f"❌ Error: {e}")


# ── Registration ──────────────────────────────────────────────────────────────

def register_bdm_handler(app) -> None:
    app.add_handler(CommandHandler("bdm", cmd_bdm))
    logger.info("[BDM] Handler /bdm registered")
