import io
from datetime import date
from core import config, db
from core.iia_client import create_authenticated_session
from core.jobio import run_job, logger

def fetch_pricelist_html(session, price_list_id: int) -> str:
    """Mengambil HTML detail master pricelist dari IIAWeb."""
    base = config.IIA_BASE_URL
    xhr_headers = {
        "Accept": "text/html, */*; q=0.01",
        "Referer": f"{base}/",
        "X-Requested-With": "XMLHttpRequest",
    }
    # Pastikan breadcrumb/session context terpasang
    session.get(f"{base}/MasterPriceLists/Index", params={"_respId": config.IIA_RESP_ID}, headers=xhr_headers, timeout=30)
    session.get(f"{base}/MasterPriceLists/changePageBreadCrumb", params={"_menuId": config.IIA_MENU_ID}, headers=xhr_headers, timeout=30)

    logger.info(f"Mengambil detail pricelist ID: {price_list_id}...")
    r = session.get(
        f"{base}/MasterPriceLists/detailPriceList",
        params={"_priceListId": price_list_id},
        headers=xhr_headers,
        timeout=60,
    )
    r.raise_for_status()
    return r.text

def parse_and_sync_plu(html_content: str) -> dict:
    import pandas as pd
    import re

    frames = pd.read_html(io.StringIO(html_content))
    # Temukan tabel item (berisi PLU dan PLU Conv.)
    target_table = None
    for df in frames:
        if "PLU" in df.columns and "PLU Conv." in df.columns:
            target_table = df
            break

    if target_table is None:
        raise ValueError("Tabel item PLU Conv. tidak ditemukan di respon HTML")

    today = date.today()
    parsed_rows = []

    for _, r in target_table.iterrows():
        kode_fg = str(r["PLU"]).strip() if pd.notna(r["PLU"]) else ""
        if not kode_fg or kode_fg == "nan":
            continue
        nama_item = str(r.get("Deskripsi Barang", "") or "").strip()
        conv_text = str(r.get("PLU Conv.", "") or "").strip()

        # Ekstrak channel IDM
        plu_idm = "0"
        for tok in re.split(r"\.(?:\s+|$)", conv_text):
            tok = tok.strip()
            if tok.startswith("IDM"):
                kode = tok[3:].strip()
                if kode and kode not in ("-", "0"):
                    plu_idm = kode
                break

        is_aktif = 1 if plu_idm != "0" else 0
        parsed_rows.append((kode_fg, nama_item, "IDM", plu_idm, is_aktif, today))

    conn = db.get_connection(config.DB_NAME)
    cur = conn.cursor()

    upsert_sql = """
        INSERT INTO ref_plu (kode_fg, nama_item, conv_channel, plu_idm, is_aktif, tgl_sync)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            nama_item = VALUES(nama_item),
            plu_idm = VALUES(plu_idm),
            is_aktif = VALUES(is_aktif),
            tgl_sync = VALUES(tgl_sync);
    """
    cur.executemany(upsert_sql, parsed_rows)
    conn.commit()

    # Pre-check deterministik: Update kasus SELISIH_BK yang kode_itemnya tidak punya PLU aktif
    logger.info("Menjalankan pre-check deterministik pada kasus SELISIH_BK...")
    cur.execute(
        """
        UPDATE kasus k
        JOIN ref_plu p ON p.kode_fg = k.kode_item AND p.conv_channel = 'IDM'
        SET k.indikasi_awal = 'plu_tidak_aktif'
        WHERE k.jenis = 'SELISIH_BK'
          AND k.status IN ('baru', 'diproses')
          AND p.is_aktif = 0;
        """
    )
    affected = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()

    logger.info(f"✓ Selesai sync {len(parsed_rows)} PLU. {affected} kasus ditandai 'plu_tidak_aktif'.")
    return {
        "status": "success",
        "total_plu_synced": len(parsed_rows),
        "kasus_plu_tidak_aktif": affected,
    }

def main():
    session = create_authenticated_session()
    html = fetch_pricelist_html(session, config.DEFAULT_PRICELIST_ID)
    return parse_and_sync_plu(html)

if __name__ == "__main__":
    run_job(main)
