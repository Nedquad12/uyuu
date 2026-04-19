"""
kons_command.py — Handler Telegram untuk /kons dan /kons2

Tampilkan bar chart klasifikasi investor (scripless shares)
berdasarkan data dari /home/ec2-user/database/klas (file Excel bulanan).

Nama file format: mmyy  (misal 0426 = April 2026)
File diurutkan berdasarkan nilai mmyy, bukan abjad.

Mode:
  /kons BBCA      → snapshot data terbaru (semua kategori non-zero)
  /kons2 BBCA     → perbandingan otomatis bulan ini vs bulan lalu

Output:
  - Semua kategori non-zero, diurutkan ascending (terkecil → terbesar)
  - Dipecah per 15 kategori → maksimal 3 chart
  - Caption dinamis hanya untuk kategori yang muncul di chart
  - Label caption dalam bahasa Inggris (sesuai kolom xlsx)

Cache di-build saat startup / reload via build_kons_cache().

Integrasi ke main.py:
    from kons_command import register_kons_handler, build_kons_cache
    build_kons_cache()          # di do_reload() dan main()
    register_kons_handler(app)  # di main()
"""

import asyncio
import calendar
import gc
import glob
import io
import logging
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode

from admin.auth import is_authorized_user, is_vip_user, check_public_group_access
from admin.admin_command import active_admins

logger = logging.getLogger(__name__)

# ── Konstanta ──────────────────────────────────────────────────────────────────
KLAS_DIR   = "/home/ec2-user/database/klas"
WATERMARK  = "Membahas Saham Indonesia"
CHART_SIZE = 15  # maksimal kategori per chart

# Semua kolom klasifikasi (urutan tidak penting — akan di-sort by value)
KLAS_COLS = [
    "BANK",
    "GOVERNMENT",
    "PRIVATE EQUITY",
    "TRUSTEE BANK",
    "VENTURE CAPITAL",
    "PRIVATE BANK",
    "EXCHANGE TRADED FUNDS",
    "INVESTMENT MANAGER",
    "INVESTMENT ADVISORS",
    "BROKERAGE FIRMS",
    "HEDGE FUND",
    "SOVEREIGN WEALTH FUND",
    "CAPITAL MARKET SUPPORTING INSTITUTIONS AND PROFESSIONS",
    "COMMANDITAIRE VENNOOTSCHAP (CV) OR LIMITED PARTNERSHIP",
    "FIRM",
    "INVESTMENT FUND SELLING AGENT",
    "PEER TO PEER LENDING",
    "PERMANENT ESTABLISHMENT",
    "SOLE PROPRIETORSHIP",
    "CORPORATE",
    "ASSOCIATION/SOCIAL ORGANIZATIONS",
    "STATE OWNED ENTERPRISES",
    "CENTRAL BANK",
    "STATE OWNED COMPANY",
    "DIOCESE",
    "CONFERENCE",
    "CONGREGATION",
    "COOPERATIVES",
    "INTERNATIONAL ORGANIZATION",
    "POLITICAL PARTIES",
    "PARTNERSHIP",
    "EDUCATIONAL INSTITUTION",
    "MUTUAL FUNDS (MF)",
    "SECURITIES COMPANY (SC)",
    "PENSION FUNDS (PF)",
    "FINANCIAL INSTITUTIONAL (IB)",
    "INSURANCE (IS)",
    "FOUNDATION (FD)",
    "INDIVIDUAL (ID)",
]

# Label pendek untuk sumbu X chart
SHORT_LABELS = {
    "BANK":                                                    "Bank",
    "GOVERNMENT":                                              "Govt",
    "PRIVATE EQUITY":                                          "PE",
    "TRUSTEE BANK":                                            "TB",
    "VENTURE CAPITAL":                                         "VC",
    "PRIVATE BANK":                                            "PrvBank",
    "EXCHANGE TRADED FUNDS":                                   "ETF",
    "INVESTMENT MANAGER":                                      "IM",
    "INVESTMENT ADVISORS":                                     "IA",
    "BROKERAGE FIRMS":                                         "BF",
    "HEDGE FUND":                                              "HF",
    "SOVEREIGN WEALTH FUND":                                   "SWF",
    "CAPITAL MARKET SUPPORTING INSTITUTIONS AND PROFESSIONS":  "CMSIP",
    "COMMANDITAIRE VENNOOTSCHAP (CV) OR LIMITED PARTNERSHIP":  "CV/LP",
    "FIRM":                                                    "Firm",
    "INVESTMENT FUND SELLING AGENT":                           "IFSA",
    "PEER TO PEER LENDING":                                    "P2P",
    "PERMANENT ESTABLISHMENT":                                 "PE-Est",
    "SOLE PROPRIETORSHIP":                                     "SP",
    "CORPORATE":                                               "Corp",
    "ASSOCIATION/SOCIAL ORGANIZATIONS":                        "Assoc",
    "STATE OWNED ENTERPRISES":                                 "SOE",
    "CENTRAL BANK":                                            "CB",
    "STATE OWNED COMPANY":                                     "SOC",
    "DIOCESE":                                                 "Diocese",
    "CONFERENCE":                                              "Conf",
    "CONGREGATION":                                            "Cong",
    "COOPERATIVES":                                            "Coop",
    "INTERNATIONAL ORGANIZATION":                              "Intl Org",
    "POLITICAL PARTIES":                                       "Parpol",
    "PARTNERSHIP":                                             "Partner",
    "EDUCATIONAL INSTITUTION":                                 "Edu",
    "MUTUAL FUNDS (MF)":                                       "MF",
    "SECURITIES COMPANY (SC)":                                 "SC",
    "PENSION FUNDS (PF)":                                      "PF",
    "FINANCIAL INSTITUTIONAL (IB)":                            "IB",
    "INSURANCE (IS)":                                          "IS",
    "FOUNDATION (FD)":                                         "FD",
    "INDIVIDUAL (ID)":                                         "ID",
}

# Full English labels for caption (matches xlsx column names)
FULL_LABELS = {
    "BANK":                                                    "Bank",
    "GOVERNMENT":                                              "Government",
    "PRIVATE EQUITY":                                          "Private Equity",
    "TRUSTEE BANK":                                            "Trustee Bank",
    "VENTURE CAPITAL":                                         "Venture Capital",
    "PRIVATE BANK":                                            "Private Bank",
    "EXCHANGE TRADED FUNDS":                                   "Exchange Traded Funds",
    "INVESTMENT MANAGER":                                      "Investment Manager",
    "INVESTMENT ADVISORS":                                     "Investment Advisors",
    "BROKERAGE FIRMS":                                         "Brokerage Firms",
    "HEDGE FUND":                                              "Hedge Fund",
    "SOVEREIGN WEALTH FUND":                                   "Sovereign Wealth Fund",
    "CAPITAL MARKET SUPPORTING INSTITUTIONS AND PROFESSIONS":  "Capital Market Supporting Institutions and Professions",
    "COMMANDITAIRE VENNOOTSCHAP (CV) OR LIMITED PARTNERSHIP":  "Commanditaire Vennootschap (CV) or Limited Partnership",
    "FIRM":                                                    "Firm",
    "INVESTMENT FUND SELLING AGENT":                           "Investment Fund Selling Agent",
    "PEER TO PEER LENDING":                                    "Peer to Peer Lending",
    "PERMANENT ESTABLISHMENT":                                 "Permanent Establishment",
    "SOLE PROPRIETORSHIP":                                     "Sole Proprietorship",
    "CORPORATE":                                               "Corporate",
    "ASSOCIATION/SOCIAL ORGANIZATIONS":                        "Association/Social Organizations",
    "STATE OWNED ENTERPRISES":                                 "State Owned Enterprises",
    "CENTRAL BANK":                                            "Central Bank",
    "STATE OWNED COMPANY":                                     "State Owned Company",
    "DIOCESE":                                                 "Diocese",
    "CONFERENCE":                                              "Conference",
    "CONGREGATION":                                            "Congregation",
    "COOPERATIVES":                                            "Cooperatives",
    "INTERNATIONAL ORGANIZATION":                              "International Organization",
    "POLITICAL PARTIES":                                       "Political Parties",
    "PARTNERSHIP":                                             "Partnership",
    "EDUCATIONAL INSTITUTION":                                 "Educational Institution",
    "MUTUAL FUNDS (MF)":                                       "Mutual Funds (MF)",
    "SECURITIES COMPANY (SC)":                                 "Securities Company (SC)",
    "PENSION FUNDS (PF)":                                      "Pension Funds (PF)",
    "FINANCIAL INSTITUTIONAL (IB)":                            "Financial Institutional (IB)",
    "INSURANCE (IS)":                                          "Insurance (IS)",
    "FOUNDATION (FD)":                                         "Foundation (FD)",
    "INDIVIDUAL (ID)":                                         "Individual (ID)",
}

CAT_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#9467bd", "#d62728",
    "#e377c2", "#8c564b", "#17becf", "#bcbd22", "#7f7f7f",
    "#aec7e8", "#ffbb78", "#98df8a", "#c5b0d5", "#f7b6d2",
]

# ── Global cache ───────────────────────────────────────────────────────────────
_kons_cache: dict = {"files": []}


# ══════════════════════════════════════════════════════════════════════════════
#  Auth guard
# ══════════════════════════════════════════════════════════════════════════════

def _is_allowed(user_id: int) -> bool:
    return is_authorized_user(user_id) or is_vip_user(user_id)


# ══════════════════════════════════════════════════════════════════════════════
#  File helpers
# ══════════════════════════════════════════════════════════════════════════════

def _mmyy_sort_key(filepath: str) -> int:
    name = os.path.splitext(os.path.basename(filepath))[0]
    m = re.fullmatch(r"(\d{2})(\d{2})", name)
    if not m:
        return 0
    mm, yy = int(m.group(1)), int(m.group(2))
    return (2000 + yy) * 100 + mm


def _parse_mmyy_label(filepath: str) -> str:
    name = os.path.splitext(os.path.basename(filepath))[0]
    m = re.fullmatch(r"(\d{2})(\d{2})", name)
    if not m:
        return name
    mm, yy = int(m.group(1)), int(m.group(2))
    return f"{calendar.month_abbr[mm]} 20{yy:02d}"


def _sorted_klas_files() -> list[str]:
    files = []
    for ext in ("*.xlsx", "*.xls", "*.XLSX", "*.XLS"):
        files.extend(glob.glob(os.path.join(KLAS_DIR, ext)))
    return sorted(files, key=_mmyy_sort_key)


def _load_file(filepath: str) -> pd.DataFrame | None:
    try:
        df = pd.read_excel(filepath, header=1)
    except Exception as e:
        logger.warning(f"[KONS] Gagal baca {filepath}: {e}")
        return None

    df.columns = [str(c).strip().upper() for c in df.columns]

    for col in list(df.columns):
        if col in ("SHARE CODE", "CODE"):
            df.rename(columns={col: "SHARE CODE"}, inplace=True)
            break

    if "SHARE CODE" not in df.columns:
        logger.error(f"[KONS] Kolom SHARE CODE tidak ditemukan di {filepath}")
        return None

    df["SHARE CODE"] = df["SHARE CODE"].astype(str).str.strip().str.upper()
    df = df[df["SHARE CODE"].str.len() <= 6].copy()

    for col in KLAS_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df


# ══════════════════════════════════════════════════════════════════════════════
#  Cache builder
# ══════════════════════════════════════════════════════════════════════════════

def build_kons_cache() -> None:
    global _kons_cache

    if not os.path.exists(KLAS_DIR):
        logger.warning(f"[KONS] Folder tidak ditemukan: {KLAS_DIR}")
        _kons_cache = {"files": []}
        return

    files = _sorted_klas_files()
    if not files:
        logger.warning(f"[KONS] Tidak ada file Excel di {KLAS_DIR}")
        _kons_cache = {"files": []}
        return

    loaded = []
    for fp in files:
        df = _load_file(fp)
        if df is not None:
            label = _parse_mmyy_label(fp)
            mmyy  = os.path.splitext(os.path.basename(fp))[0]
            loaded.append((mmyy, label, df))
            logger.info(f"[KONS] Cached {os.path.basename(fp)} ({len(df)} rows)")

    _kons_cache = {"files": loaded}
    logger.info(f"[KONS] Cache selesai: {len(loaded)} file(s)")


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _get_nonzero_sorted(row: pd.Series) -> list[tuple[str, float]]:
    """
    Return list (col, value) non-zero, diurutkan ascending by value
    (terkecil di kiri, terbesar di kanan).
    """
    result = []
    for col in KLAS_COLS:
        if col in row.index:
            val = float(row.get(col, 0))
            if val > 0:
                result.append((col, val))
    return sorted(result, key=lambda x: x[1])


def _build_caption(cols: list[str]) -> str:
    """Buat caption hanya untuk kolom yang muncul di chart."""
    lines = []
    for col in cols:
        short = SHORT_LABELS.get(col, col[:8])
        full  = FULL_LABELS.get(col, col)
        lines.append(f"{short}={full}")
    return "\n".join(lines)


def _make_single_chart(
    entries: list[tuple[str, float]],
    ticker: str,
    date_label: str,
    chart_num: int,
    total_charts: int,
) -> io.BytesIO:
    """Buat satu bar chart dari list (col, value), sudah di-sort ascending."""
    labels = [SHORT_LABELS.get(c, c[:8]) for c, _ in entries]
    values = [v for _, v in entries]
    colors = [CAT_COLORS[i % len(CAT_COLORS)] for i in range(len(entries))]

    suffix = f" ({chart_num}/{total_charts})" if total_charts > 1 else ""
    fig, ax = plt.subplots(figsize=(max(10, len(entries) * 0.9), 6))
    fig.patch.set_facecolor("white")
    fig.suptitle(
        f"Investor Classification — {ticker.upper()}{suffix}\n{date_label}",
        fontsize=13, fontweight="bold", y=1.02,
    )

    x    = range(len(labels))
    bars = ax.bar(x, values, color=colors, edgecolor="white", linewidth=0.8)

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=9)
    ax.set_title("Scripless Shares by Investor Type", fontsize=11, fontweight="bold")
    ax.set_ylabel("Shares")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))

    for bar, val in zip(bars, values):
        off = max(val * 0.01, 1)
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            val + off,
            f"{val:,.0f}", ha="center", va="bottom", fontsize=7.5, fontweight="bold",
        )

    ax.grid(axis="y", alpha=0.3)
    fig.text(0.5, 0.5, WATERMARK, fontsize=40, color="gray",
             ha="center", va="center", alpha=0.10, rotation=30,
             transform=fig.transFigure, zorder=0)

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=180, bbox_inches="tight", facecolor="white")
    buf.seek(0)
    plt.close(fig)
    gc.collect()
    return buf


def _make_snapshot_charts(
    row: pd.Series, ticker: str, date_label: str
) -> list[tuple[io.BytesIO, str]]:
    """
    Return list of (buf, caption) per chart.
    Dibagi per CHART_SIZE kategori, diurutkan ascending by value.
    """
    sorted_entries = _get_nonzero_sorted(row)
    if not sorted_entries:
        raise ValueError(f"All categories are zero for {ticker}")

    # Pecah per CHART_SIZE
    chunks = [
        sorted_entries[i: i + CHART_SIZE]
        for i in range(0, len(sorted_entries), CHART_SIZE)
    ]
    total = len(chunks)
    result = []

    for idx, chunk in enumerate(chunks, 1):
        buf     = _make_single_chart(chunk, ticker, date_label, idx, total)
        cols    = [c for c, _ in chunk]
        caption = (
            f"📊 <b>Investor Classification — {ticker}</b>"
            + (f" ({idx}/{total})" if total > 1 else "")
            + f"\n\n{_build_caption(cols)}"
        )
        result.append((buf, caption))

    return result


def _make_comparison_charts(
    row_new: pd.Series,
    row_old: pd.Series,
    ticker: str,
    date_new: str,
    date_old: str,
) -> list[tuple[io.BytesIO, str]]:
    """
    Bar chart perubahan (absolut + %) mirip /forc.
    Skip kategori jika KEDUANYA new dan old = 0.
    Dibagi per CHART_SIZE kategori, diurutkan ascending by abs(delta).
    """
    all_entries = []
    for col in KLAS_COLS:
        if col not in row_new.index:
            continue
        v_new = float(row_new.get(col, 0))
        v_old = float(row_old.get(col, 0))
        if v_new == 0 and v_old == 0:
            continue
        delta = v_new - v_old
        pct   = delta / v_old * 100 if v_old != 0 else 0.0
        all_entries.append((col, delta, pct, v_old))

    if not all_entries:
        raise ValueError(f"All categories are zero for {ticker}")

    # Sort ascending by abs delta
    all_entries.sort(key=lambda x: abs(x[1]))

    chunks = [
        all_entries[i: i + CHART_SIZE]
        for i in range(0, len(all_entries), CHART_SIZE)
    ]
    total  = len(chunks)
    result = []

    for idx, chunk in enumerate(chunks, 1):
        labels = [SHORT_LABELS.get(c, c[:8]) for c, _, _, _ in chunk]
        deltas = [d for _, d, _, _ in chunk]
        pcts   = [p for _, _, p, _ in chunk]
        colors = ["#2ecc71" if d >= 0 else "#e74c3c" for d in deltas]

        suffix = f" ({idx}/{total})" if total > 1 else ""
        fig, (ax_abs, ax_pct) = plt.subplots(1, 2, figsize=(16, 6))
        fig.patch.set_facecolor("white")
        fig.suptitle(
            f"Investor Classification Change — {ticker.upper()}{suffix}\n"
            f"{date_old}  →  {date_new}",
            fontsize=13, fontweight="bold", y=1.02,
        )

        x = range(len(labels))

        # Panel kiri: absolut
        bars = ax_abs.bar(x, deltas, color=colors, edgecolor="white", linewidth=0.8)
        ax_abs.axhline(0, color="#555555", linewidth=0.8, linestyle="--")
        ax_abs.set_xticks(list(x))
        ax_abs.set_xticklabels(labels, rotation=30, ha="right", fontsize=9)
        ax_abs.set_title("Absolute Change (shares)", fontsize=11, fontweight="bold")
        ax_abs.set_ylabel("Shares")
        ax_abs.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
        for bar, val in zip(bars, deltas):
            if val == 0:
                continue
            va  = "bottom" if val >= 0 else "top"
            off = max(abs(val) * 0.02, 1)
            ax_abs.text(
                bar.get_x() + bar.get_width() / 2,
                val + (off if val >= 0 else -off),
                f"{val:+,.0f}", ha="center", va=va, fontsize=7.5, fontweight="bold",
            )
        ax_abs.grid(axis="y", alpha=0.3)

        # Panel kanan: %
        bars2 = ax_pct.bar(x, pcts, color=colors, edgecolor="white", linewidth=0.8)
        ax_pct.axhline(0, color="#555555", linewidth=0.8, linestyle="--")
        ax_pct.set_xticks(list(x))
        ax_pct.set_xticklabels(labels, rotation=30, ha="right", fontsize=9)
        ax_pct.set_title("Change (%)", fontsize=11, fontweight="bold")
        ax_pct.set_ylabel("Percentage (%)")
        ax_pct.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:+.1f}%"))
        for bar, val in zip(bars2, pcts):
            if val == 0:
                continue
            va  = "bottom" if val >= 0 else "top"
            off = max(abs(val) * 0.02, 0.1)
            ax_pct.text(
                bar.get_x() + bar.get_width() / 2,
                val + (off if val >= 0 else -off),
                f"{val:+.1f}%", ha="center", va=va, fontsize=7.5, fontweight="bold",
            )
        ax_pct.grid(axis="y", alpha=0.3)

        fig.text(0.5, 0.5, WATERMARK, fontsize=40, color="gray",
                 ha="center", va="center", alpha=0.10, rotation=30,
                 transform=fig.transFigure, zorder=0)

        plt.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=180, bbox_inches="tight", facecolor="white")
        buf.seek(0)
        plt.close(fig)
        gc.collect()

        cols    = [c for c, _, _, _ in chunk]
        caption = (
            f"📊 <b>Classification Change — {ticker}</b>"
            + (f" ({idx}/{total})" if total > 1 else "")
            + f"\n\n{_build_caption(cols)}"
        )
        result.append((buf, caption))

    return result


# ══════════════════════════════════════════════════════════════════════════════
#  Public entry point
# ══════════════════════════════════════════════════════════════════════════════

def create_kons_charts(
    ticker: str, n: int = 0
) -> tuple[list[tuple[io.BytesIO, str]], str]:
    """
    Return (list of (buf, caption), fallback_msg).
      n=0  → snapshot terbaru
      n≥1  → perbandingan n bulan ke belakang
    """
    files = _kons_cache.get("files", [])
    if not files:
        return [], ""

    # ── Snapshot ──
    if n == 0 or len(files) == 1:
        fallback_msg = ""
        if n > 0 and len(files) == 1:
            fallback_msg = "⚠️ Comparison data not yet available (only 1 month). Showing latest snapshot.\n\n"

        _, date_label, df = files[-1]
        sub = df[df["SHARE CODE"] == ticker.upper()]
        if sub.empty:
            return [], ""
        charts = _make_snapshot_charts(sub.iloc[0], ticker, date_label)
        return charts, fallback_msg

    # ── Perbandingan ──
    if n >= len(files):
        actual_n     = len(files) - 1
        fallback_msg = (
            f"⚠️ Only {len(files)} month(s) of data available. "
            f"Showing {actual_n}-month comparison.\n\n"
        )
    else:
        actual_n     = n
        fallback_msg = ""

    _, date_new, df_new = files[-1]
    _, date_old, df_old = files[-(actual_n + 1)]

    sub_new = df_new[df_new["SHARE CODE"] == ticker.upper()]
    sub_old = df_old[df_old["SHARE CODE"] == ticker.upper()]

    if sub_new.empty or sub_old.empty:
        return [], ""

    charts = _make_comparison_charts(
        sub_new.iloc[0], sub_old.iloc[0],
        ticker, date_new, date_old,
    )
    return charts, fallback_msg


# ══════════════════════════════════════════════════════════════════════════════
#  Telegram handler
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_kons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /kons TICKER [N]
    N = bulan pembanding (default 0 = snapshot, max 5).
    """
    if not await check_public_group_access(update, active_admins):
        return

    uid = update.effective_user.id
    if not _is_allowed(uid):
        await update.message.reply_text("⛔ You do not have access to this feature.")
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "⚠️ Usage: <code>/kons TICKER [N]</code>\n"
            "Example: <code>/kons BBCA</code> or <code>/kons BBCA 2</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    ticker = args[0].upper().strip()
    n = 0
    if len(args) >= 2:
        try:
            n = max(0, min(5, int(args[1])))
        except ValueError:
            pass

    msg = await update.message.reply_text(
        f"⏳ Building classification chart for <b>{ticker}</b>…",
        parse_mode=ParseMode.HTML,
    )

    try:
        charts, fallback_msg = await asyncio.get_event_loop().run_in_executor(
            None, lambda: create_kons_charts(ticker, n)
        )

        if not charts:
            await msg.edit_text(
                f"❌ Data for <b>{ticker}</b> not found.",
                parse_mode=ParseMode.HTML,
            )
            return

        await msg.delete()

        for i, (buf, caption) in enumerate(charts):
            # Sisipkan fallback_msg hanya di chart pertama
            full_caption = (fallback_msg if i == 0 else "") + caption
            await update.message.reply_photo(
                photo=buf,
                caption=full_caption,
                parse_mode=ParseMode.HTML,
            )

    except ValueError as e:
        await msg.edit_text(f"⚠️ {e}", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"[KONS] Error {ticker}: {e}", exc_info=True)
        await msg.edit_text(
            f"❌ Failed to build chart for <b>{ticker}</b>.\n<code>{e}</code>",
            parse_mode=ParseMode.HTML,
        )


async def cmd_kons2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /kons2 TICKER
    Perbandingan otomatis antara bulan ini dan bulan lalu.
    File dibaca berdasarkan nama mmyy.xlsx dari KLAS_DIR.
    """
    if not await check_public_group_access(update, active_admins):
        return

    uid = update.effective_user.id
    if not _is_allowed(uid):
        await update.message.reply_text("⛔ You do not have access to this feature.")
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "⚠️ Usage: <code>/kons2 TICKER</code>\n"
            "Example: <code>/kons2 BBCA</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    ticker = args[0].upper().strip()

    msg = await update.message.reply_text(
        f"⏳ Building comparison chart for <b>{ticker}</b>…",
        parse_mode=ParseMode.HTML,
    )

    try:
        files = _kons_cache.get("files", [])

        if len(files) < 2:
            await msg.edit_text(
                "⚠️ Not enough data for comparison. At least 2 months of data required.",
                parse_mode=ParseMode.HTML,
            )
            return

        _, date_new, df_new = files[-1]
        _, date_old, df_old = files[-2]

        sub_new = df_new[df_new["SHARE CODE"] == ticker]
        sub_old = df_old[df_old["SHARE CODE"] == ticker]

        if sub_new.empty or sub_old.empty:
            await msg.edit_text(
                f"❌ Data for <b>{ticker}</b> not found.",
                parse_mode=ParseMode.HTML,
            )
            return

        charts = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: _make_comparison_charts(
                sub_new.iloc[0], sub_old.iloc[0],
                ticker, date_new, date_old,
            ),
        )

        if not charts:
            await msg.edit_text(
                f"❌ Failed to build chart for <b>{ticker}</b>.",
                parse_mode=ParseMode.HTML,
            )
            return

        await msg.delete()

        for buf, caption in charts:
            await update.message.reply_photo(
                photo=buf,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )

    except ValueError as e:
        await msg.edit_text(f"⚠️ {e}", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"[KONS2] Error {ticker}: {e}", exc_info=True)
        await msg.edit_text(
            f"❌ Failed to build chart for <b>{ticker}</b>.\n<code>{e}</code>",
            parse_mode=ParseMode.HTML,
        )


def register_kons_handler(app) -> None:
    """Daftarkan handler /kons dan /kons2 ke Application. Panggil dari main.py."""
    app.add_handler(CommandHandler("kons", cmd_kons))
    app.add_handler(CommandHandler("kons2", cmd_kons2))
