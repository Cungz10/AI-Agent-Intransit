import io
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
from mysql.connector import Error
import mysql.connector

# ── LOAD ENV ──────────────────────────────────────────────────────────────────
load_dotenv(Path(__file__).parent / ".env")

# ── KONFIGURASI WEB ───────────────────────────────────────────────────────────
BASE_URL  = os.environ["IIA_BASE_URL"]
LOGIN_URL = os.environ["IIA_LOGIN_URL"]
USERNAME  = os.environ["IIA_USERNAME"]
PASSWORD  = os.environ["IIA_PASSWORD"]
RESP_ID   = os.environ.get("IIA_RESP_ID", "91")

# ── KONFIGURASI DB ────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host":     os.environ.get("DB_HOST",     "localhost"),
    "port":     int(os.environ.get("DB_PORT", 3306)),
    "user":     os.environ.get("DB_USER",     "root"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": os.environ.get("DB_NAME",     "admin_dashboard2"),
}

# DB kedua — insert data yang sama juga ke sini
DB_CONFIG_2 = {
    "host":     os.environ.get("DB2_HOST",     os.environ.get("DB_HOST", "localhost")),
    "port":     int(os.environ.get("DB2_PORT", os.environ.get("DB_PORT", 3306))),
    "user":     os.environ.get("DB2_USER",     os.environ.get("DB_USER", "root")),
    "password": os.environ.get("DB2_PASSWORD", os.environ.get("DB_PASSWORD", "")),
    "database": os.environ.get("DB2_NAME",     "admin_dashboard3"),
}

# ── PERIODE ───────────────────────────────────────────────────────────────────
# Rutin harian via n8n: selalu ambil H-1 dari hari ini
h2 = date.today() - timedelta(days=1)

def fmt_date(d: date) -> str:
    # Format: 01-June-2026 (zero-padded day, sesuai URL IIAWeb)
    return f"{d.day:02d}-{d.strftime('%B-%Y')}"

# ── TABLE & SQL ───────────────────────────────────────────────────────────────
TABLE_NAME = "rekap_selisih_bk"

INSERT_SQL = f"""
    INSERT INTO {TABLE_NAME}
        (tipe, periode_start, periode_end, no_urut, kode_fg, nama_produk, kdcab, kdtk,
         nama_toko, nonota, tgl_kirim, qty_sj, nilai_sj, no_btb,
         qty_bpb, nilai_btb, qty_selisih, nilai_selisih, source_file)
    VALUES
        (%(tipe)s, %(periode_start)s, %(periode_end)s, %(no_urut)s, %(kode_fg)s, %(nama_produk)s,
         %(kdcab)s, %(kdtk)s, %(nama_toko)s, %(nonota)s, %(tgl_kirim)s,
         %(qty_sj)s, %(nilai_sj)s, %(no_btb)s, %(qty_bpb)s, %(nilai_btb)s, %(qty_selisih)s,
         %(nilai_selisih)s, %(source_file)s)
    ON DUPLICATE KEY UPDATE
        tipe=VALUES(tipe), periode_start=VALUES(periode_start), periode_end=VALUES(periode_end),
        no_urut=VALUES(no_urut), nama_produk=VALUES(nama_produk), kdcab=VALUES(kdcab),
        nama_toko=VALUES(nama_toko), tgl_kirim=VALUES(tgl_kirim),
        qty_sj=VALUES(qty_sj), nilai_sj=VALUES(nilai_sj), no_btb=VALUES(no_btb),
        qty_bpb=VALUES(qty_bpb), nilai_btb=VALUES(nilai_btb),
        qty_selisih=VALUES(qty_selisih), nilai_selisih=VALUES(nilai_selisih),
        source_file=VALUES(source_file);
    """


# ── LOGIN ─────────────────────────────────────────────────────────────────────
class TokenParser(HTMLParser):
    """Parse CSRF token dari halaman login."""
    def __init__(self):
        super().__init__()
        self.token = None

    def handle_starttag(self, tag, attrs):
        if tag == "input":
            d = dict(attrs)
            if d.get("name") == "__RequestVerificationToken":
                self.token = d.get("value")


def login(session: requests.Session) -> None:
    print("[INFO] Ambil CSRF token...", file=sys.stderr)
    resp = session.get(LOGIN_URL, timeout=30)
    resp.raise_for_status()

    p = TokenParser()
    p.feed(resp.text)
    if not p.token:
        raise ValueError("CSRF token tidak ditemukan di halaman login!")

    print(f"[INFO] Login sebagai {USERNAME}...", file=sys.stderr)
    resp = session.post(
        LOGIN_URL,
        data={
            "__RequestVerificationToken": p.token,
            "Username":   USERNAME,
            "Password":   PASSWORD,
            "RememberMe": "false",
        },
        timeout=30,
        allow_redirects=True,
    )

    if "login" in resp.url.lower():
        raise ValueError("Login gagal! Cek username/password di .env.")

    print("[INFO] Login berhasil!", file=sys.stderr)


# ── RETRY HELPER ──────────────────────────────────────────────────────────────
MAX_RETRIES  = 3
RETRY_DELAY  = 30  # detik, dikali attempt ke- (backoff linear: 30s, 60s, 90s)


def login_and_download() -> bytes:
    """Login + download dengan retry. Session dibikin baru tiap percobaan,
    soalnya kalau gagal di tengah download, session lama bisa aja udah gak valid."""
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            session = requests.Session()
            session.headers.update({"User-Agent": "Mozilla/5.0"})
            login(session)
            return download_excel(session)
        except (requests.exceptions.RequestException, ValueError) as e:
            last_err = e
            print(f"[WARN] Percobaan {attempt}/{MAX_RETRIES} gagal: {e}", file=sys.stderr)
            if attempt < MAX_RETRIES:
                delay = RETRY_DELAY * attempt
                print(f"[INFO] Retry dalam {delay} detik...", file=sys.stderr)
                time.sleep(delay)

    raise RuntimeError(f"Login/download gagal setelah {MAX_RETRIES}x percobaan: {last_err}")


# ── DOWNLOAD ──────────────────────────────────────────────────────────────────
def download_excel(session: requests.Session) -> bytes:
    """Download file Excel H-2 langsung ke memory (bytes)."""
    url = (
        f"{BASE_URL}/reports/printRekapIntransit"
        f"?_startDate={fmt_date(h2)}&_endDate={fmt_date(h2)}"
        f"&_respId={RESP_ID}&_isDetail=true"
    )
    print(f"[INFO] Download tanggal: {fmt_date(h2)}", file=sys.stderr)
    print(f"[INFO] URL: {url}", file=sys.stderr)

    resp = session.get(
        url,
        timeout=(30, 3600),  # connect 30s, read 1 jam (report-nya emang lama)
        stream=True,
    )
    if resp.status_code != 200:
        raise ValueError(f"Download gagal, HTTP {resp.status_code}")

    chunks = []
    downloaded = 0
    for chunk in resp.iter_content(chunk_size=1024 * 64):
        if chunk:
            chunks.append(chunk)
            downloaded += len(chunk)
            print(f"[INFO] Downloaded: {downloaded / 1024:.1f} KB...", end="\r", file=sys.stderr)

    content = b"".join(chunks)
    print(f"\n[OK]  Download selesai ({len(content) / 1024:.1f} KB)", file=sys.stderr)
    return content


# ── PARSE EXCEL ───────────────────────────────────────────────────────────────
def parse_date(value, fmt="%d-%B-%Y"):
    if pd.isna(value):
        return None
    return datetime.strptime(str(value).strip(), fmt).date()


def classify_jenis_masalah(raw_value) -> str | None:
    s = str(raw_value).strip().upper()
    if "INTRANSIT" in s:
        return "Intransit"
    if "SELISIH" in s:
        return "Selisih BK"
    return None


def parse_excel(content: bytes, source_filename: str) -> list:
    """
    Parse bytes Excel → flat list of rows (semua masuk satu tabel dengan kolom tipe).
    source_filename dipakai untuk kolom source_file.
    """
    raw = pd.read_excel(io.BytesIO(content), header=None)

    # Ambil periode dari baris judul (baris index 1)
    title_row = str(raw.iat[1, 0])
    m = re.search(r"(\d{2}-\w+-\d{4})\s+s/d\s+(\d{2}-\w+-\d{4})", title_row)
    if not m:
        raise ValueError(f"Format periode tidak ditemukan di judul: '{title_row}'")

    periode_start = parse_date(m.group(1))
    periode_end   = parse_date(m.group(2))
    print(f"[INFO] Periode terdeteksi: {periode_start} s/d {periode_end}", file=sys.stderr)

    rows          = []
    kode_fg       = None
    nama_produk   = None
    unknown_jenis = set()

    for _, r in raw.iloc[4:].iterrows():
        col0, col1 = r[0], r[1]

        # Baris header produk: col0 kosong, col1 = "KODE NAMA_PRODUK"
        if pd.isna(col0) and pd.notna(col1):
            s     = str(col1).strip()
            parts = s.split(" ", 1)
            kode_fg     = parts[0]
            nama_produk = parts[1] if len(parts) > 1 else ""
            continue

        # Baris total → skip
        if isinstance(col0, str) and col0.strip().lower() == "total":
            continue

        # Baris data: col0 adalah angka (no_urut)
        if pd.notna(col0) and str(col0).strip().replace(".0", "").isdigit():
            tipe = classify_jenis_masalah(r[5])
            if tipe is None:
                unknown_jenis.add(str(r[5]))
                continue

            rows.append({
                "tipe":          tipe,
                "periode_start": periode_start,
                "periode_end":   periode_end,
                "no_urut":       int(float(col0)),
                "kode_fg":       kode_fg,
                "nama_produk":   nama_produk,
                "kdcab":         r[1],
                "kdtk":          r[2],
                "nama_toko":     r[3],
                "nonota":        str(r[4]) if pd.notna(r[4]) else None,
                "tgl_kirim":     parse_date(r[6]),
                "qty_sj":        int(r[7])   if pd.notna(r[7])  else 0,
                "nilai_sj":      float(r[8]) if pd.notna(r[8])  else 0,
                "no_btb":        str(r[9])   if pd.notna(r[9])  else None,
                "qty_bpb":       int(r[10])  if pd.notna(r[10]) else 0,
                "nilai_btb":     float(r[11]) if pd.notna(r[11]) else 0,
                "qty_selisih":   int(r[12])  if pd.notna(r[12]) else 0,
                "nilai_selisih": float(r[13]) if pd.notna(r[13]) else 0,
                "source_file":   source_filename,
            })

    if unknown_jenis:
        print(f"[WARN] JENIS MASALAH tidak dikenal (di-skip): {unknown_jenis}", file=sys.stderr)

    intransit_count = sum(1 for r in rows if r["tipe"] == "Intransit")
    selisih_count   = sum(1 for r in rows if r["tipe"] == "Selisih BK")
    print(f"[INFO] Total baris ter-parse: {len(rows)} ({intransit_count} Intransit, {selisih_count} Selisih BK)", file=sys.stderr)
    return rows


# ── INSERT KE DB ──────────────────────────────────────────────────────────────
def insert_rows_to(db_config: dict, rows: list) -> tuple:
    """Insert ke satu DB spesifik. Dipanggil terpisah per DB biar gagal di satu
    DB gak bikin DB lain ikut ke-skip."""
    conn = mysql.connector.connect(**db_config)
    cur  = conn.cursor()

    if rows:
        cur.executemany(INSERT_SQL, rows)

    affected = cur.rowcount if rows else 0
    conn.commit()
    cur.close()
    conn.close()
    return len(rows), affected


def insert_rows(rows: list) -> list:
    """Insert rows yang sama ke semua DB target (DB_CONFIG & DB_CONFIG_2).
    Return list of dict berisi hasil/error per DB, biar main() bisa lapor jelas
    dan tetap lanjut walau salah satu DB gagal."""
    targets = [
        ("admin_dashboard2 (utama)", DB_CONFIG),
        ("admin_dashboard3 (kedua)", DB_CONFIG_2),
    ]

    results = []
    for label, cfg in targets:
        try:
            count, affected = insert_rows_to(cfg, rows)
            results.append({"label": label, "ok": True, "count": count, "affected": affected})
        except Error as e:
            results.append({"label": label, "ok": False, "error": str(e)})

    return results


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    print(f"[INFO] Target tanggal: {fmt_date(h2)} (H-2 dari hari ini)", file=sys.stderr)

    # 1. Login & download (dengan retry otomatis kalau server timeout/hiccup)
    try:
        content = login_and_download()
    except RuntimeError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Parse
    source_filename = f"Rekap_Intransit_{h2.strftime('%Y%m%d')}.xlsx"
    print("[INFO] Parsing data Excel...", file=sys.stderr)
    rows = parse_excel(content, source_filename)

    if not rows:
        print("[WARN] Tidak ada data untuk tanggal ini.", file=sys.stderr)
        sys.exit(0)

    # 3. Insert ke DB (utama + kedua)
    print("[INFO] Insert ke MySQL...", file=sys.stderr)
    results = insert_rows(rows)

    any_ok = False
    for r in results:
        if r["ok"]:
            any_ok = True
            print(
                f"[OK]  `{TABLE_NAME}` @ {r['label']}: {r['count']} baris diproses, "
                f"{r['affected']} baris affected.",
                file=sys.stderr,
            )
        else:
            print(f"[ERROR] Gagal konek/insert ke MySQL ({r['label']}): {r['error']}", file=sys.stderr)

    if not any_ok:
        # Kalau kedua DB gagal semua, baru dianggap fail total
        sys.exit(1)

    print("[DONE] Selesai!", file=sys.stderr)


if __name__ == "__main__":
    main()
