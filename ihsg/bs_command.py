"""
bs_command.py
=============
Handler /bs — Broker Summary dari neobdm.tech.
Output: gambar tabel (mirip UI neobdm) dengan buy side kiri, sell side kanan.

Usage:
    /bs 010226 170426 BBCA           → val all
    /bs 010226 170426 BBCA net       → mode net
    /bs 010226 170426 BBCA f         → filter foreign
    /bs 010226 170426 BBCA net f     → net foreign

Format tanggal: ddmmyy — contoh 010226 = 01 Feb 2026
"""

import os
import sys
import io
import logging
import asyncio
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode

from admin.auth import is_authorized_user, is_vip_user
from neobdm import NeoBDM

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
TOP_N = 20

# ── Warna (dark UI mirip neobdm) ───────────────────────────────────────────────
C_BG       = "#0d1117"
C_HEADER   = "#161b22"
C_ROW_ODD  = "#0d1117"
C_ROW_EVEN = "#111920"
C_DIVIDER  = "#1e2a38"
C_FOOTER   = "#0a1628"
C_TITLE    = "#e6edf3"
C_HEAD_TXT = "#8b949e"
C_BUY      = "#3fb950"
C_SELL     = "#f85149"
C_RANK     = "#8b949e"
C_BORDER   = "#30363d"
C_FOOT_LBL = "#8b949e"

# ── Session singleton ──────────────────────────────────────────────────────────
_neo: Optional[NeoBDM] = None

def _get_neo() -> NeoBDM:
    global _neo
    if _neo is None:
        _neo = NeoBDM()
        _neo.login()
        logger.info("[BS] Login neobdm OK")
    return _neo


# ── Auth ───────────────────────────────────────────────────────────────────────
def _is_allowed(uid: int) -> bool:
    return is_authorized_user(uid) or is_vip_user(uid)


# ── Parse tanggal ddmmyy ───────────────────────────────────────────────────────
def _parse_ddmmyy(s: str) -> str:
    s = s.strip()
    if len(s) != 6 or not s.isdigit():
        raise ValueError(f"Format tanggal salah: '{s}' — harus ddmmyy, contoh: 170426")
    try:
        dt = datetime.strptime(f"{s[:2]}{s[2:4]}20{s[4:]}", "%d%m%Y")
    except ValueError:
        raise ValueError(f"Tanggal tidak valid: '{s}'")
    return dt.strftime("%d %b %Y")


# ── Fetch ──────────────────────────────────────────────────────────────────────
def _fetch(ticker: str, start: str, end: str) -> dict:
    neo = _get_neo()
    return neo.get_broker_summary(ticker, start, end)


# ── Renderer ───────────────────────────────────────────────────────────────────

def _clean(s: str) -> str:
    return (s or "").strip().lstrip("-").strip() or "-"


def _parse_num(s: str) -> float:
    """Parse angka dari string neobdm: '1.234.567' atau '124.9B' → float."""
    if not s or s.strip() in ("-", ""):
        return 0.0
    try:
        s = s.strip().lstrip("-").upper()
        mult = 1.0
        if s.endswith("B"):
            mult = 1_000_000_000
            s = s[:-1]
        elif s.endswith("M"):
            mult = 1_000_000
            s = s[:-1]
        s = s.replace(".", "").replace(",", "")
        return float(s) * mult
    except Exception:
        return 0.0


def _fmt_num(v: float) -> str:
    """Format float ke string ringkas: 1234567 → '1.234.567'."""
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1_000_000_000:
        return f"{sign}{v/1_000_000_000:.1f}B"
    if v >= 1_000_000:
        return f"{sign}{v/1_000_000:.1f}M"
    # Format ribuan dengan titik
    return f"{sign}{v:,.0f}".replace(",", ".")


def _build_net_map(rows: list) -> dict:
    """
    Gabungkan buy dan sell per broker yang sama dari semua rows.
    Return { broker: {buy_lot, sell_lot, buy_val, sell_val, sell_avg} }
    """
    bmap: dict[str, dict] = {}
    for row in rows:
        b = row.get("buy_broker", "").strip()
        if b and b != "-":
            e = bmap.setdefault(b, {"buy_lot": 0.0, "sell_lot": 0.0,
                                    "buy_val": 0.0,  "sell_val": 0.0,
                                    "sell_avg": ""})
            e["buy_lot"] += _parse_num(row.get("buy_lot", "0"))
            e["buy_val"] += _parse_num(row.get("buy_val", "0"))

        s = row.get("sell_broker", "").strip()
        if s and s != "-":
            e = bmap.setdefault(s, {"buy_lot": 0.0, "sell_lot": 0.0,
                                    "buy_val": 0.0,  "sell_val": 0.0,
                                    "sell_avg": ""})
            e["sell_lot"] += _parse_num(row.get("sell_lot", "0"))
            e["sell_val"] += _parse_num(row.get("sell_val", "0"))
            if not e["sell_avg"] and row.get("sell_avg", ""):
                e["sell_avg"] = _clean(row.get("sell_avg", ""))
    return bmap


def compute_net_sides(rows: list, top_n: int = TOP_N) -> tuple[list, list]:
    """
    Return (buy_side, sell_side) — masing-masing top_n baris.

    buy_side  : broker dengan net_lot > 0, sort desc by net_lot
    sell_side : broker dengan net_lot < 0, sort asc by net_lot (terbesar jualnya dulu)

    Setiap item: { broker, net_lot, net_val, sell_avg }
    """
    bmap = _build_net_map(rows)

    buy_side  = []
    sell_side = []

    for broker, v in bmap.items():
        net_lot = v["buy_lot"] - v["sell_lot"]
        net_val = v["buy_val"] - v["sell_val"]
        entry = {
            "broker":   broker,
            "net_lot":  net_lot,
            "net_val":  net_val,
            "sell_avg": v["sell_avg"] or "-",
        }
        if net_lot >= 0:
            buy_side.append(entry)
        else:
            sell_side.append(entry)

    buy_side.sort(key=lambda x: x["net_lot"], reverse=True)
    sell_side.sort(key=lambda x: x["net_lot"])   # paling negatif dulu

    return buy_side[:top_n], sell_side[:top_n]


def build_table_image(data: dict, key: str = "val_all", top_n: int = TOP_N) -> bytes:
    """
    Render tabel dua sisi mirip UI neobdm:
      BUY side (kiri) | # | SELL side (kanan)

    Kolom kiri  : BROKER | NET LOT | NET VAL
    Kolom tengah: #
    Kolom kanan : BROKER | NET LOT | NET VAL | S.AVG

    Footer (dihitung dari data): T.LOT | T.VAL | NET LOT | NET VAL
    """
    raw_rows = data.get(key, [])
    if not raw_rows:
        raise ValueError(
            f"Tidak ada data untuk '{key}'.\n"
            "Ticker salah atau tidak ada transaksi di periode ini."
        )

    ticker     = data.get("ticker", "?")
    start_date = data.get("start_date", "")
    end_date   = data.get("end_date", "")

    buy_side, sell_side = compute_net_sides(raw_rows, top_n=top_n)
    n_rows = max(len(buy_side), len(sell_side))

    # Footer — hitung dari semua broker (sebelum split top_n)
    bmap = _build_net_map(raw_rows)
    total_lot = sum(v["buy_lot"] + v["sell_lot"] for v in bmap.values()) / 2  # hindari double count
    total_val = sum(v["buy_val"] + v["sell_val"] for v in bmap.values()) / 2
    net_lot   = sum(v["buy_lot"] - v["sell_lot"] for v in bmap.values())
    net_val   = sum(v["buy_val"] - v["sell_val"] for v in bmap.values())

    # ── Layout ────────────────────────────────────────────────────────────────
    ROW_H   = 0.36
    HEAD_H  = 0.42
    TITLE_H = 0.52
    FOOT_H  = 0.55
    FIG_W   = 13.0
    FIG_H   = TITLE_H + HEAD_H + n_rows * ROW_H + FOOT_H

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    fig.patch.set_facecolor(C_BG)
    ax.set_facecolor(C_BG)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    def to_y(offset_inch):
        return 1.0 - offset_inch / FIG_H

    def draw_rect(y_top_inch, h_inch, color):
        h = h_inch / FIG_H
        ax.add_patch(plt.Rectangle((0, to_y(y_top_inch + h_inch)), 1, h,
                                   transform=ax.transAxes,
                                   facecolor=color, zorder=1, clip_on=False))

    def txt(x, y_mid_inch, text, color, size, align="left", bold=False):
        ha = align if align in ("left", "right", "center") else "left"
        ax.text(x, to_y(y_mid_inch), str(text),
                transform=ax.transAxes, color=color, fontsize=size,
                fontweight="bold" if bold else "normal",
                ha=ha, va="center", zorder=3,
                fontfamily="monospace", clip_on=False)

    def hline(y_inch, lw=0.4, color=C_BORDER):
        ax.axhline(to_y(y_inch), color=color, linewidth=lw, zorder=2)

    def vline(x, lw=0.7, color=C_DIVIDER):
        ax.axvline(x, color=color, linewidth=lw, zorder=2)

    # ── Kolom layout (mirip neobdm) ───────────────────────────────────────────
    # BUY side kiri: BROKER | NET LOT | NET VAL
    # Tengah: #
    # SELL side kanan: BROKER | NET LOT | NET VAL | S.AVG
    #
    # x positions (0..1):
    BUY_BROKER = (0.000, 0.075, "left")
    BUY_LOT    = (0.075, 0.095, "right")
    BUY_VAL    = (0.170, 0.095, "right")
    RANK_COL   = (0.265, 0.038, "center")
    SEL_BROKER = (0.303, 0.075, "left")
    SEL_LOT    = (0.378, 0.095, "right")
    SEL_VAL    = (0.473, 0.095, "right")
    SEL_AVG    = (0.568, 0.075, "right")

    def cx(col, pad=0.008):
        x0, w, align = col
        if align == "left":   return x0 + pad
        if align == "right":  return x0 + w - pad
        return x0 + w / 2

    # ── TITLE ─────────────────────────────────────────────────────────────────
    y = 0.0
    draw_rect(y, TITLE_H, C_HEADER)
    mid = y + TITLE_H / 2
    txt(0.5,   mid, f"{start_date}  —  {end_date}", C_TITLE, 11, "center", bold=True)
    mode_label = key.replace("_", " ").upper()
    txt(0.985, mid, f"{ticker}  |  {mode_label}", C_HEAD_TXT, 8.5, "right")
    hline(y + TITLE_H, lw=0.6)
    y += TITLE_H

    # ── HEADER ────────────────────────────────────────────────────────────────
    draw_rect(y, HEAD_H, C_HEADER)
    mid = y + HEAD_H / 2
    # Buy side headers
    txt(cx(BUY_BROKER), mid, "BUY",     C_BUY,      8, "left",   bold=True)
    txt(cx(BUY_LOT),    mid, "NET LOT", C_BUY,      8, "right",  bold=True)
    txt(cx(BUY_VAL),    mid, "NET VAL", C_BUY,      8, "right",  bold=True)
    txt(cx(RANK_COL),   mid, "#",       C_HEAD_TXT, 8, "center", bold=True)
    # Sell side headers
    txt(cx(SEL_BROKER), mid, "SELL",    C_SELL,     8, "left",   bold=True)
    txt(cx(SEL_LOT),    mid, "NET LOT", C_SELL,     8, "right",  bold=True)
    txt(cx(SEL_VAL),    mid, "NET VAL", C_SELL,     8, "right",  bold=True)
    txt(cx(SEL_AVG),    mid, "S.AVG",   C_SELL,     8, "right",  bold=True)
    hline(y + HEAD_H, lw=0.5)
    y += HEAD_H

    # Divider vertikal di kiri dan kanan kolom rank
    vline(RANK_COL[0],                  lw=0.8)
    vline(RANK_COL[0] + RANK_COL[1],    lw=0.8)

    # ── ROWS ──────────────────────────────────────────────────────────────────
    for ri in range(n_rows):
        bg = C_ROW_EVEN if ri % 2 == 0 else C_ROW_ODD
        draw_rect(y, ROW_H, bg)
        mid = y + ROW_H / 2
        rank = str(ri + 1)

        # BUY side
        if ri < len(buy_side):
            b = buy_side[ri]
            txt(cx(BUY_BROKER), mid, b["broker"],          C_BUY,   8.5, "left")
            txt(cx(BUY_LOT),    mid, _fmt_num(b["net_lot"]), C_BUY,   8.5, "right")
            txt(cx(BUY_VAL),    mid, _fmt_num(b["net_val"]), C_BUY,   8.5, "right")

        # Rank
        txt(cx(RANK_COL), mid, rank, C_RANK, 8, "center")

        # SELL side
        if ri < len(sell_side):
            s = sell_side[ri]
            txt(cx(SEL_BROKER), mid, s["broker"],                    C_SELL, 8.5, "left")
            txt(cx(SEL_LOT),    mid, _fmt_num(abs(s["net_lot"])),    C_SELL, 8.5, "right")
            txt(cx(SEL_VAL),    mid, _fmt_num(abs(s["net_val"])),    C_SELL, 8.5, "right")
            txt(cx(SEL_AVG),    mid, s["sell_avg"],                  C_SELL, 8.5, "right")

        hline(y + ROW_H, lw=0.25)
        y += ROW_H

    # ── FOOTER ────────────────────────────────────────────────────────────────
    hline(y, lw=0.8)
    draw_rect(y, FOOT_H, C_FOOTER)
    mid = y + FOOT_H / 2

    nl_color = C_BUY  if net_lot >= 0 else C_SELL
    nv_color = C_BUY  if net_val >= 0 else C_SELL

    footer = [
        ("T.LOT", _fmt_num(total_lot), C_TITLE),
        ("T.VAL", _fmt_num(total_val), C_TITLE),
        ("NET LOT", _fmt_num(net_lot), nl_color),
        ("NET VAL", _fmt_num(net_val), nv_color),
    ]
    for fi, (label, value, vc) in enumerate(footer):
        fx = (fi + 0.5) / len(footer)
        txt(fx, mid - FOOT_H * 0.18, label, C_FOOT_LBL, 7.5, "center")
        txt(fx, mid + FOOT_H * 0.12, value, vc,         10.5, "center", bold=True)

    # ── Border ────────────────────────────────────────────────────────────────
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.add_patch(plt.Rectangle((0, 0), 1, 1, fill=False,
                               edgecolor=C_BORDER, linewidth=1.5,
                               transform=ax.transAxes, zorder=5))

    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150,
                bbox_inches="tight", pad_inches=0.05,
                facecolor=C_BG)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ── Command handler ────────────────────────────────────────────────────────────

USAGE = (
    "⚠️ <b>Usage /bs:</b>\n"
    "<code>/bs 010226 170426 BBCA</code>\n"
    "<code>/bs 010226 170426 BBCA net</code>\n"
    "<code>/bs 010226 170426 BBCA f</code>   — foreign\n"
    "<code>/bs 010226 170426 BBCA d</code>   — domestic\n"
    "<code>/bs 010226 170426 BBCA net f</code>\n\n"
    "Format: <code>ddmmyy</code>"
)


async def cmd_bs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/bs ddmmyy ddmmyy TICKER [net] [f/d]"""
    uid = update.effective_user.id
    if not _is_allowed(uid):
        await update.message.reply_text("⛔ Akses ditolak.")
        return

    args = context.args or []
    if len(args) < 3:
        await update.message.reply_text(USAGE, parse_mode=ParseMode.HTML)
        return

    try:
        start = _parse_ddmmyy(args[0])
        end   = _parse_ddmmyy(args[1])
    except ValueError as e:
        await update.message.reply_text(f"❌ {e}", parse_mode=ParseMode.HTML)
        return

    ticker = args[2].upper()
    flags  = [a.lower() for a in args[3:]]

    mode = "net" if "net" in flags else "val"
    if any(f in flags for f in ("f", "foreign", "asing")):
        fda = "F"
    elif any(f in flags for f in ("d", "domestic", "lokal")):
        fda = "D"
    else:
        fda = "A"

    fda_label = {"A": "All", "F": "Foreign", "D": "Domestic"}[fda]
    key = f"{mode}_{'all' if fda=='A' else 'foreign' if fda=='F' else 'domestic'}"

    wait_msg = await update.message.reply_text(
        f"⏳ Fetching <b>{ticker}</b> · {mode.upper()} · {fda_label} "
        f"<code>{start} → {end}</code>",
        parse_mode=ParseMode.HTML,
    )

    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: _fetch(ticker, start, end))
        img  = await loop.run_in_executor(None, lambda: build_table_image(data, key=key, top_n=TOP_N))

        caption = (
            f"📊 <b>{ticker}</b>  ·  {mode.upper()} {fda_label}\n"
            f"<code>{data.get('start_date', start)} → {data.get('end_date', end)}</code>"
        )
        await update.message.reply_photo(photo=img, caption=caption, parse_mode=ParseMode.HTML)
        await wait_msg.delete()

    except ValueError as e:
        await wait_msg.edit_text(f"⚠️ {e}")
    except PermissionError as e:
        await wait_msg.edit_text(f"❌ Login neobdm gagal: {e}")
    except Exception as e:
        logger.exception("[BS] Error: %s", e)
        await wait_msg.edit_text(f"❌ Error: {e}")


# ── Registration ───────────────────────────────────────────────────────────────

def register_bs_handler(app) -> None:
    app.add_handler(CommandHandler("bs", cmd_bs))
    logger.info("[BS] Handler /bs registered")
