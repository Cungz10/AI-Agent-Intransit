import json
from core import config, db
from core.jobio import run_job, logger

TEMPLATE_TAGIHAN_CABANG = """
Halo Rekan-rekan Cabang *{nama_cabang}* {mentions_str} 🙏

Mohon bantuan pengecekan dan tindak lanjut untuk dokumen kiriman berikut yang masih berstatus terbuka:

{daftar_nota}

Mohon dapat segera diproses atau berikan konfirmasi kendala jika ada kendala sistem / penerimaan fisik.
Terima kasih atas kerjasamanya! 🙏
""".strip()

def draft_messages_per_cabang(run_id: int) -> dict:
    conn = db.get_connection(config.DB_NAME)
    cur = conn.cursor(dictionary=True)

    # Ambil cabang yang memiliki kasus aktif dan belum memiliki pesan aktif
    cur.execute(
        """
        SELECT 
            c.kode_cabang,
            c.nama_cabang
        FROM master_cabang c
        JOIN v_kasus_dokumen d ON d.kode_cabang = c.kode_cabang
        LEFT JOIN antrian_pesan a 
            ON a.kode_cabang = c.kode_cabang 
            AND a.status IN ('draft', 'menunggu_approval', 'disetujui', 'mengirim')
        WHERE a.id IS NULL
        GROUP BY c.kode_cabang, c.nama_cabang
        """
    )
    cabang_list = cur.fetchall()

    if not cabang_list:
        logger.info("Tidak ada cabang yang membutuhkan draft pesan baru saat ini.")
        cur.close()
        conn.close()
        return {"status": "no_pending_drafts", "total_drafted": 0}

    # Ambil target JID grup gabungan dari config
    target_jid = config.TARGET_GROUP_JIDS[0] if config.TARGET_GROUP_JIDS else ""
    if not target_jid:
        raise ValueError("TARGET_GROUP_JIDS belum dikonfigurasi di .env")

    draft_created = 0

    for cb in cabang_list:
        kdcab = cb["kode_cabang"]
        nama_cabang = cb["nama_cabang"]

        # 1. Cari PIC utama cabang untuk di-mention
        cur.execute(
            """
            SELECT nomor_wa, nama_pic 
            FROM master_pic 
            WHERE kode_cabang = %s AND is_aktif = 1
            ORDER BY urutan_kontak ASC
            LIMIT 1
            """,
            (kdcab,),
        )
        pic_row = cur.fetchone()
        mentions = [pic_row["nomor_wa"]] if pic_row else []
        mentions_str = f"(@{pic_row['nomor_wa']})" if pic_row else ""

        # 2. Ambil daftar nota terbuka di cabang ini
        cur.execute(
            """
            SELECT kasus_id_perwakilan AS id, docno, kode_toko, nama_toko, jenis, total_nilai, umur_hari
            FROM v_kasus_dokumen
            WHERE kode_cabang = %s
            ORDER BY total_nilai DESC
            LIMIT 10
            """,
            (kdcab,),
        )
        dokumen_items = cur.fetchall()

        if not dokumen_items:
            continue

        daftar_nota_lines = []
        kasus_ids = []
        for i, doc in enumerate(dokumen_items, start=1):
            nilai_fmt = f"Rp {doc['total_nilai']:,.0f}".replace(",", ".")
            daftar_nota_lines.append(
                f"{i}. *{doc['docno']}* ({doc['kode_toko']} - {doc['nama_toko']})\n"
                f"   Jenis: {doc['jenis']} | Umur: {doc['umur_hari']} hari | Nilai: {nilai_fmt}"
            )
            # Ambil semua id kasus perwakilan
            kasus_ids.append(doc["id"])

        pesan_final = TEMPLATE_TAGIHAN_CABANG.format(
            nama_cabang=nama_cabang,
            mentions_str=mentions_str,
            daftar_nota="\n\n".join(daftar_nota_lines),
        )

        # 3. Simpan ke antrian_pesan
        cur.execute(
            """
            INSERT INTO antrian_pesan (
                kode_cabang, target_jid, mentions, jenis_pesan, pesan, status
            ) VALUES (%s, %s, %s, 'tagihan_awal', %s, 'menunggu_approval')
            """,
            (kdcab, target_jid, json.dumps(mentions), pesan_final),
        )
        pesan_id = cur.lastrowid

        # 4. Hubungkan relasi kasus di antrian_pesan_kasus
        for k_id in kasus_ids:
            cur.execute(
                """
                INSERT IGNORE INTO antrian_pesan_kasus (pesan_id, kasus_id)
                VALUES (%s, %s)
                """,
                (pesan_id, k_id),
            )

        draft_created += 1

    conn.commit()
    cur.close()
    conn.close()

    logger.info(f"✓ Berhasil membuat {draft_created} draft pesan baru.")
    return {"status": "success", "total_drafted": draft_created}

def main():
    run_id = db.start_agent_run("Collector", pemicu="jadwal")
    try:
        res = draft_messages_per_cabang(run_id)
        db.finish_agent_run(run_id, status="selesai", detail=res)
        return res
    except Exception as e:
        db.finish_agent_run(run_id, status="gagal", error=str(e))
        raise

if __name__ == "__main__":
    run_job(main)
