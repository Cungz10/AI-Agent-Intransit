import sys
import re
from core import config, db
from core.jobio import run_job, logger

def handle_inbound_message(sender_wa: str, message_body: str, group_jid: str = "") -> dict:
    """
    Menyimpan balasan pesan dari PIC grup ke tabel riwayat_tindakan.
    """
    clean_sender = re.sub(r"[^\d]", "", sender_wa)
    logger.info(f"Menerima balasan dari {clean_sender} di grup {group_jid}: {message_body}")

    conn = db.get_connection(config.DB_NAME)
    cur = conn.cursor(dictionary=True)

    # Identifikasi PIC
    cur.execute(
        """
        SELECT p.kode_cabang, p.nama_pic, c.nama_cabang
        FROM master_pic p
        JOIN master_cabang c ON c.kode_cabang = p.kode_cabang
        WHERE p.nomor_wa = %s AND p.is_aktif = 1
        LIMIT 1
        """,
        (clean_sender,),
    )
    pic_info = cur.fetchone()

    actor_name = pic_info["nama_pic"] if pic_info else f"PIC ({clean_sender})"
    kode_cabang = pic_info["kode_cabang"] if pic_info else None

    # Cari kasus aktif terkait di cabang tersebut untuk dicatat ke riwayatnya
    recorded_count = 0
    if kode_cabang:
        cur.execute(
            """
            SELECT id FROM kasus
            WHERE kode_cabang = %s AND status = 'menunggu_pic'
            """,
            (kode_cabang,),
        )
        kasus_rows = cur.fetchall()
        for k in kasus_rows:
            db.log_riwayat(
                kasus_id=k["id"],
                tindakan="terima_balasan",
                actor_type="pic",
                actor_name=actor_name,
                catatan=f"Balasan di grup: {message_body}",
                conn=conn,
            )
            recorded_count += 1
        conn.commit()

    cur.close()
    conn.close()

    return {
        "status": "success",
        "sender": clean_sender,
        "nama_pic": actor_name,
        "kode_cabang": kode_cabang,
        "kasus_terkait": recorded_count,
    }

def main():
    if len(sys.argv) < 3:
        return {"status": "error", "message": "Usage: python -m jobs.inbound_handler <sender> <message> [group_jid]"}
    sender = sys.argv[1]
    msg = sys.argv[2]
    grp = sys.argv[3] if len(sys.argv) > 3 else ""
    return handle_inbound_message(sender, msg, grp)

if __name__ == "__main__":
    run_job(main)
