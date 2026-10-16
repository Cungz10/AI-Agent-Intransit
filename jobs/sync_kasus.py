from datetime import date, timedelta
from core import config, db
from core.jobio import run_job, logger

def check_data_readiness(conn) -> tuple[bool, str]:
    """
    Mengecek apakah:
    1. Snapshot hari ini sudah terisi di intransit_agent.snapshot_intransit
    2. Data rekap_selisih_bk di admin_dashboard3 sudah ada data terbaru (H-1)
    """
    today = date.today()
    h1 = today - timedelta(days=1)

    cur = conn.cursor()
    # 1. Cek snapshot hari ini
    cur.execute("SELECT COUNT(*) FROM snapshot_intransit WHERE tgl_snapshot = %s", (today,))
    snap_count = cur.fetchone()[0]
    if snap_count == 0:
        cur.close()
        return False, f"Snapshot untuk hari ini ({today}) belum ada. Jalankan snapshot_open terlebih dahulu."

    # 2. Cek data di admin_dashboard3
    try:
        cur.execute(f"SELECT MAX(periode_end) FROM {config.DB_SOURCE_NAME}.rekap_selisih_bk")
        max_periode = cur.fetchone()[0]
        if not max_periode or max_periode < h1:
            cur.close()
            return False, f"Data di {config.DB_SOURCE_NAME}.rekap_selisih_bk belum update H-1 (terakhir: {max_periode}, butuh minimal: {h1})."
    except Exception as e:
        cur.close()
        return False, f"Gagal mengecek {config.DB_SOURCE_NAME}.rekap_selisih_bk: {e}"

    cur.close()
    return True, "Data siap"

def sync_data(run_id: int) -> dict:
    today = date.today()
    ambang_tgl = today - timedelta(days=config.AMBANG_INTRANSIT_HARI)

    conn = db.get_connection(config.DB_NAME)

    ready, msg = check_data_readiness(conn)
    if not ready:
        logger.warning(f"Data belum siap untuk sinkronisasi: {msg}")
        return {"status": "waiting_data", "message": msg}

    cur = conn.cursor(dictionary=True)

    # -----------------------------------------------------------------
    # 1. Upsert kasus baru dari admin_dashboard3.rekap_selisih_bk
    # Filter:
    # - Hanya nota yang aktif di snapshot_intransit hari ini
    # - Jenis SELISIH_BK langsung masuk
    # - Jenis INTRANSIT hanya jika tgl_kirim <= ambang (H-3)
    # -----------------------------------------------------------------
    logger.info("Mengambil kandidat kasus dari rekap_selisih_bk & snapshot...")
    query_kandidat = f"""
        SELECT 
            b.kdcab AS kode_cabang,
            b.kdtk AS kode_toko,
            b.nama_toko,
            b.nonota AS docno,
            COALESCE(b.kode_fg, '') AS kode_item,
            b.nama_produk AS nama_item,
            COALESCE(b.qty_selisih, 0) AS qty,
            COALESCE(b.nilai_selisih, 0) AS nilai,
            b.tgl_kirim AS tgl_dokumen,
            CASE 
                WHEN UPPER(b.tipe) LIKE '%INTRANSIT%' THEN 'INTRANSIT'
                WHEN UPPER(b.tipe) LIKE '%SELISIH%' THEN 'SELISIH_BK'
                ELSE 'LAINNYA'
            END AS jenis
        FROM {config.DB_SOURCE_NAME}.rekap_selisih_bk b
        JOIN snapshot_intransit s 
            ON s.docno = b.nonota COLLATE utf8mb4_unicode_ci
            AND s.kode_toko = b.kdtk COLLATE utf8mb4_unicode_ci
            AND s.tgl_snapshot = %s
        WHERE (
            UPPER(b.tipe) LIKE '%SELISIH%'
            OR (UPPER(b.tipe) LIKE '%INTRANSIT%' AND b.tgl_kirim <= %s)
        )
    """
    cur.execute(query_kandidat, (today, ambang_tgl))
    kandidat_rows = cur.fetchall()
    logger.info(f"Ditemukan {len(kandidat_rows)} baris kandidat kasus.")

    upsert_sql = """
        INSERT INTO kasus (
            jenis, kode_cabang, kode_toko, nama_toko, docno, kode_item, nama_item,
            qty, nilai, tgl_dokumen, terakhir_terlihat, status, prioritas, sumber
        ) VALUES (
            %(jenis)s, %(kode_cabang)s, %(kode_toko)s, %(nama_toko)s, %(docno)s, %(kode_item)s, %(nama_item)s,
            %(qty)s, %(nilai)s, %(tgl_dokumen)s, %(terakhir_terlihat)s, 'baru', 'sedang', 'rekap_selisih_bk'
        )
        ON DUPLICATE KEY UPDATE
            nama_toko = VALUES(nama_toko),
            nama_item = VALUES(nama_item),
            qty = VALUES(qty),
            nilai = VALUES(nilai),
            terakhir_terlihat = VALUES(terakhir_terlihat),
            updated_at = CURRENT_TIMESTAMP;
    """

    for row in kandidat_rows:
        cur.execute(upsert_sql, {**row, "terakhir_terlihat": today})

    conn.commit()

    # -----------------------------------------------------------------
    # 2. Reopen Check:
    # Kasus yang sebelumnya status = 'selesai', tapi docno-nya muncul lagi di snapshot hari ini
    # -----------------------------------------------------------------
    logger.info("Mengecek kasus berstatus 'selesai' yang muncul kembali (reopen)...")
    cur.execute(
        """
        SELECT k.id, k.docno, k.kode_toko, k.jenis
        FROM kasus k
        JOIN snapshot_intransit s 
            ON s.docno = k.docno 
            AND s.kode_toko = k.kode_toko 
            AND s.tgl_snapshot = %s
        WHERE k.status = 'selesai'
        """,
        (today,),
    )
    reopen_candidates = cur.fetchall()
    reopen_count = 0
    for r in reopen_candidates:
        cur.execute(
            """
            UPDATE kasus 
            SET status = 'baru', resolved_at = NULL, terakhir_terlihat = %s 
            WHERE id = %s
            """,
            (today, r["id"]),
        )
        db.log_riwayat(
            kasus_id=r["id"],
            tindakan="reopen",
            actor_type="system",
            actor_name="sync_kasus",
            status_sebelum="selesai",
            status_sesudah="baru",
            catatan="Kasus muncul kembali pada rekap kumulatif hari ini",
            run_id=run_id,
            conn=conn,
        )
        reopen_count += 1

    conn.commit()
    logger.info(f"Kasus di-reopen: {reopen_count}")

    # -----------------------------------------------------------------
    # 3. Auto-Close Check dengan Safeguards:
    # Kasus berstatus bukan 'selesai' tapi docno-nya TIDAK ada di snapshot hari ini
    # -----------------------------------------------------------------
    logger.info("Mengecek kasus aktif yang hilang dari snapshot hari ini (auto-close)...")
    cur.execute("SELECT COUNT(*) AS total_aktif FROM kasus WHERE status <> 'selesai'")
    total_aktif = cur.fetchone()["total_aktif"]

    cur.execute(
        """
        SELECT k.id, k.docno, k.kode_toko, k.status
        FROM kasus k
        LEFT JOIN snapshot_intransit s 
            ON s.docno = k.docno 
            AND s.kode_toko = k.kode_toko 
            AND s.tgl_snapshot = %s
        WHERE k.status <> 'selesai'
          AND s.id IS NULL
        """,
        (today,),
    )
    close_candidates = cur.fetchall()
    close_count = len(close_candidates)
    logger.info(f"Kandidat auto-close: {close_count} dari total aktif {total_aktif}")

    auto_close_ditahan = False
    closed_final = 0

    if total_aktif > 0 and (close_count / total_aktif) > 0.30:
        # Guardrail triggered! Jangan auto-close massal sebelum diverifikasi
        auto_close_ditahan = True
        logger.warning(
            f"⚠️ PENGAMAN AKTIF: Kandidat auto-close ({close_count}/{total_aktif} = "
            f"{(close_count/total_aktif)*100:.1f}%) melebihi batas 30%! Auto-close ditahan."
        )
    else:
        for r in close_candidates:
            cur.execute(
                """
                UPDATE kasus 
                SET status = 'selesai', resolved_at = CURRENT_TIMESTAMP 
                WHERE id = %s
                """,
                (r["id"],),
            )
            db.log_riwayat(
                kasus_id=r["id"],
                tindakan="auto_close",
                actor_type="system",
                actor_name="sync_kasus",
                status_sebelum=r["status"],
                status_sesudah="selesai",
                catatan="Nomor nota sudah hilang dari rekap kumulatif (sudah di-BPB/selesai)",
                run_id=run_id,
                conn=conn,
            )
            closed_final += 1
        conn.commit()

    cur.close()
    conn.close()

    return {
        "status": "success",
        "kandidat_diproses": len(kandidat_rows),
        "reopen_count": reopen_count,
        "auto_close_count": closed_final,
        "auto_close_ditahan": auto_close_ditahan,
        "calon_close_ditahan": close_count if auto_close_ditahan else 0,
    }

def main():
    run_id = db.start_agent_run("sync_kasus", pemicu="jadwal")
    try:
        res = sync_data(run_id)
        db.finish_agent_run(run_id, status="selesai", detail=res)
        return res
    except Exception as e:
        db.finish_agent_run(run_id, status="gagal", error=str(e))
        raise

if __name__ == "__main__":
    run_job(main)
