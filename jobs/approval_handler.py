import sys
import re
from core import config, db
from core.jobio import run_job, logger

def process_command(sender_wa: str, message_body: str) -> dict:
    """
    Memproses perintah balasan approval dari OWNER_WA:
    - OK <id>               -> Approve pesan
    - TOLAK <id> <alasan>   -> Tolak pesan
    - EDIT <id> <isi_baru>  -> Ubah isi pesan
    """
    clean_sender = re.sub(r"[^\d]", "", sender_wa)
    clean_owner = re.sub(r"[^\d]", "", config.OWNER_WA)

    if not clean_owner or clean_sender != clean_owner:
        logger.warning(f"Akses ditolak: Pengirim {clean_sender} bukan OWNER_WA ({clean_owner}).")
        return {"status": "unauthorized", "message": "Bukan nomor owner yang sah."}

    text = message_body.strip()
    logger.info(f"Menerima perintah approval: {text}")

    conn = db.get_connection(config.DB_NAME)
    cur = conn.cursor(dictionary=True)

    # 1. OK <id>
    match_ok = re.match(r"^OK\s+(\d+)$", text, re.IGNORECASE)
    if match_ok:
        pesan_id = int(match_ok.group(1))
        cur.execute(
            """
            UPDATE antrian_pesan
            SET status = 'disetujui',
                approved_by = 'Owner',
                approved_at = CURRENT_TIMESTAMP
            WHERE id = %s AND status = 'menunggu_approval'
            """,
            (pesan_id,),
        )
        conn.commit()
        affected = cur.rowcount
        cur.close()
        conn.close()
        return {
            "status": "success",
            "action": "approve",
            "pesan_id": pesan_id,
            "success": affected > 0,
        }

    # 2. TOLAK <id> <alasan>
    match_tolak = re.match(r"^TOLAK\s+(\d+)(?:\s+(.+))?$", text, re.IGNORECASE)
    if match_tolak:
        pesan_id = int(match_tolak.group(1))
        alasan = match_tolak.group(2) or "Ditolak manual oleh owner"
        cur.execute(
            """
            UPDATE antrian_pesan
            SET status = 'ditolak',
                rejected_reason = %s
            WHERE id = %s AND status = 'menunggu_approval'
            """,
            (alasan, pesan_id),
        )
        conn.commit()
        affected = cur.rowcount
        cur.close()
        conn.close()
        return {
            "status": "success",
            "action": "reject",
            "pesan_id": pesan_id,
            "success": affected > 0,
        }

    cur.close()
    conn.close()
    return {"status": "ignored", "message": "Pola perintah tidak cocok (OK / TOLAK)."}

def main():
    if len(sys.argv) < 3:
        return {"status": "error", "message": "Usage: python -m jobs.approval_handler <sender> <message>"}
    sender = sys.argv[1]
    msg = " ".join(sys.argv[2:])
    return process_command(sender, msg)

if __name__ == "__main__":
    run_job(main)
