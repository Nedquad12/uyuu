"""
neobdm.py
=========
Modul untuk ambil data Broker Summary dari neobdm.tech.

Session management:
- Login sekali, session tetap hidup (tidak logout)
- CSRF token di-reuse dari cookie selama session valid
- Kalau response bukan JSON (session expired) → reset session + relogin
- Reset session = buat Session() baru yang bersih (bukan logout ke server)
"""

import os
import time
import random
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Optional, Union

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

_DELAY_MIN = 1.5
_DELAY_MAX = 3.0


def _fmt_date(d: Union[str, datetime]) -> str:
    if isinstance(d, datetime):
        return d.strftime("%d %b %Y")
    return d


def _delay():
    time.sleep(random.uniform(_DELAY_MIN, _DELAY_MAX))


class NeoBDM:

    BASE_URL = "https://neobdm.tech"

    def __init__(self, username: str = None, password: str = None):
        self.username = username or os.getenv("NEOBDM_EMAIL")
        self.password = password or os.getenv("NEOBDM_PASSWORD")

        if not self.username or not self.password:
            raise ValueError(
                "Username/password tidak ditemukan.\n"
                "Buat file .env:\n"
                "  NEOBDM_EMAIL=email@gmail.com\n"
                "  NEOBDM_PASSWORD=passwordkamu"
            )

        self._logged_in = False
        self._init_session()

    def _init_session(self):
        """Buat requests.Session baru yang bersih."""
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
        })

    def _reset_session(self):
        """
        Buang session lama (cookie expired dll), buat session baru.
        INI BUKAN LOGOUT — tidak kirim request logout ke server.
        Dipanggil hanya kalau server kasih response invalid (session expired di sisi server).
        """
        try:
            self._session.close()
        except Exception:
            pass
        self._logged_in = False
        self._init_session()
        logger.info("[NeoBDM] Session lokal di-reset (bukan logout)")

    # ── Auth ──────────────────────────────────────────────────────────────────

    def login(self) -> bool:
        """Login ke neobdm.tech. Session tetap hidup setelah ini."""
        r = self._session.get(f"{self.BASE_URL}/accounts/login/", timeout=10)
        r.raise_for_status()

        csrf = self._parse_csrf(r.text)
        if not csrf:
            raise RuntimeError("CSRF token tidak ditemukan di halaman login")

        r = self._session.post(
            f"{self.BASE_URL}/accounts/login/",
            data={
                "csrfmiddlewaretoken": csrf,
                "login":              self.username,
                "password":           self.password,
            },
            headers={
                "Referer": f"{self.BASE_URL}/accounts/login/",
                "Origin":  self.BASE_URL,
            },
            allow_redirects=True,
            timeout=10,
        )

        if "accounts/login" in r.url:
            raise PermissionError("Login gagal — username/password salah")

        self._logged_in = True
        logger.info("[NeoBDM] Login berhasil, session aktif")
        return True

    def _ensure_logged_in(self):
        if not self._logged_in:
            self.login()

    # ── Public API ────────────────────────────────────────────────────────────

    def get_broker_summary(
        self,
        ticker: str,
        start_date: Union[str, datetime],
        end_date: Union[str, datetime],
    ) -> dict:
        """Ambil broker summary lengkap: semua kombinasi Val/Net x All/F/D."""
        self._ensure_logged_in()

        start = _fmt_date(start_date)
        end   = _fmt_date(end_date)

        combos = {
            "val_all":      ("val", "A"),
            "val_foreign":  ("val", "F"),
            "val_domestic": ("val", "D"),
            "net_all":      ("net", "A"),
            "net_foreign":  ("net", "F"),
            "net_domestic": ("net", "D"),
        }

        result = {
            "ticker":     ticker.upper(),
            "start_date": start,
            "end_date":   end,
            "summary":    {},
        }

        for i, (key, (mode, fda)) in enumerate(combos.items()):
            if i > 0:
                _delay()

            raw = self._fetch_with_relogin(ticker, start, end, mode, fda)

            result["start_date"] = raw.get("start_date", start)
            result["end_date"]   = raw.get("end_date", end)

            if key == "val_all" and raw.get("summary"):
                result["summary"] = raw["summary"]

            result[key] = self._parse_table(raw.get("broksum_html", ""))

        return result

    def get_ticker_list(self) -> list:
        self._ensure_logged_in()
        r = self._session.get(
            f"{self.BASE_URL}/broker_summary/ticker-choices/",
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _fetch_with_relogin(self, ticker, start, end, mode, fda) -> dict:
        """
        Fetch satu combo.
        Kalau session expired (server tolak): reset session lokal + login ulang + retry.
        """
        try:
            return self._fetch(ticker, start, end, mode, fda)
        except PermissionError:
            logger.warning("[NeoBDM] Session expired di server, reset + re-login...")
            self._reset_session()   # buang cookie lama, buat session baru
            self.login()            # login ulang
            return self._fetch(ticker, start, end, mode, fda)

    def _fetch(self, ticker, start_date, end_date, mode, fda) -> dict:
        """Satu request ke /api/broker-summary. Reuse CSRF dari cookie session."""
        csrf = self._get_csrf()

        r = self._session.post(
            f"{self.BASE_URL}/api/broker-summary",
            data={
                "tick":                  ticker.upper(),
                "start_date":            start_date,
                "end_date":              end_date,
                "event":                 "load",
                "foreign_only":          fda == "F",
                "domestic_only":         fda == "D",
                "net":                   "true" if mode == "net" else "false",
                "show_broker_inventory": False,
                "csrfmiddlewaretoken":   csrf,
            },
            headers={
                "Referer":     f"{self.BASE_URL}/broker_summary/",
                "Origin":      self.BASE_URL,
                "X-CSRFToken": csrf,
            },
            timeout=15,
        )
        r.raise_for_status()

        ct = r.headers.get("Content-Type", "")
        if "application/json" not in ct:
            body = r.text[:300].lower()
            if "accounts/login" in r.url or "login" in body:
                self._logged_in = False
                raise PermissionError("Session expired — server redirect ke login")
            raise ValueError(
                f"Response bukan JSON (Content-Type: {ct})\n"
                f"URL: {r.url}\nBody: {r.text[:200]}"
            )

        data = r.json()
        if not data.get("success"):
            raise ValueError(
                f"API gagal: {ticker} {mode} {fda} ({start_date} -> {end_date})"
            )

        return data

    def _get_csrf(self) -> str:
        """
        Ambil CSRF token dari cookie session yang sudah ada.
        Kalau belum ada (baru login / cookie hilang), fetch halaman sekali.
        """
        # Reuse cookie csrftoken — valid selama session server masih hidup
        csrf = self._session.cookies.get("csrftoken")
        if csrf:
            return csrf

        # Cookie belum ada — fetch halaman sekali untuk dapat cookie
        r = self._session.get(f"{self.BASE_URL}/broker_summary/", timeout=10)
        if "accounts/login" in r.url:
            self._logged_in = False
            raise PermissionError("Session expired saat ambil CSRF")

        # Coba dari cookie dulu (Django set via Set-Cookie)
        csrf = self._session.cookies.get("csrftoken", "")
        if csrf:
            return csrf

        # Fallback: parse dari HTML
        csrf = self._parse_csrf(r.text)
        if csrf:
            return csrf

        raise RuntimeError("CSRF token tidak ditemukan")

    def _parse_csrf(self, html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "html.parser")
        tag = soup.find("input", {"name": "csrfmiddlewaretoken"})
        return tag["value"] if tag else None

    def _parse_table(self, html: str) -> list:
        """
        Parse tabel broker summary.

        Kolom HTML (9 kolom):
          0=BUY  1=B.LOT  2=B.VAL  3=B.AVG  4=#  5=SELL  6=S.LOT  7=S.VAL  8=S.AVG
        """
        soup  = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        if not table:
            return []

        rows = []
        for i, tr in enumerate(table.find_all("tr")[1:]):
            cells = [td.get_text(strip=True) for td in tr.find_all("td")]
            if len(cells) < 8:
                continue

            if len(cells) >= 9:
                buy_broker  = cells[0]
                buy_lot     = cells[1]
                buy_val     = cells[2]
                buy_avg     = cells[3]
                rank        = cells[4]
                sell_broker = cells[5]
                sell_lot    = cells[6]
                sell_val    = cells[7]
                sell_avg    = cells[8] if len(cells) > 8 else ""
            else:
                buy_broker  = cells[0]
                buy_lot     = cells[1]
                buy_val     = cells[2]
                buy_avg     = ""
                rank        = cells[3]
                sell_broker = cells[4]
                sell_lot    = cells[5]
                sell_val    = cells[6]
                sell_avg    = cells[7] if len(cells) > 7 else ""

            rows.append({
                "rank":        rank or str(i + 1),
                "buy_broker":  buy_broker,
                "buy_lot":     buy_lot,
                "buy_val":     buy_val,
                "buy_avg":     buy_avg,
                "sell_broker": sell_broker,
                "sell_lot":    sell_lot,
                "sell_val":    sell_val,
                "sell_avg":    sell_avg,
            })

        return rows

    def _to_float(self, s: str) -> float:
        try:
            if not s or s == "-":
                return 0.0
            s = s.strip().upper()
            mult = 1
            if "B" in s:
                mult = 1_000_000_000
                s = s.replace("B", "")
            elif "M" in s:
                mult = 1_000_000
                s = s.replace("M", "")
            if s.startswith("(") and s.endswith(")"):
                s = "-" + s[1:-1]
            s = s.replace(".", "").replace(",", "")
            return float(s) * mult
        except Exception:
            return 0.0


# ══════════════════════════════════════════════════════════════════════════════
#  Singleton — shared instance, login sekali untuk semua module
# ══════════════════════════════════════════════════════════════════════════════

_instance: Optional[NeoBDM] = None

def get_instance() -> NeoBDM:
    """
    Return singleton NeoBDM. Login otomatis kalau belum.
    Semua module (bs_command, api_server, dll) pakai ini.
    """
    global _instance
    if _instance is None:
        _instance = NeoBDM()
        _instance.login()
    return _instance
