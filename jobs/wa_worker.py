import json
import time
import random
from core import config, db, wa_client
from core.jobio import run_job, logger

def process_approved_queue(run_id: int) -> dict:
    conn = db.get_connection(config.DB_NAME)
    cur = conn.cursor(dictionary=True)

    # Ambil pesan yang sudah disetujui
    cur.execute(
        """
        SELECT id, kode_cabang, target_jid, mentions, pesan
        FROM antrian_pesan
        WHERE status = 'disetujui'
        ORDER BY scheduled_at ASC, id ASC
        """
    )
    approved_messages = cur.fetchall()

    if not approved_messages:
        logger.info("Tidak ada pesan berstatus 'disetujui' dalam antrian.")
        cur.close()
        conn.close()
        return {"status": "no_approved_messages", "sent": 0}

    sent_count = 0
    cancelled_count = 0

    for msg in approved_messages:
        pesan_id = msg["id"]

        # -------------------------------------------------------------
        # 1. Kunci baris dengan atomic update ke status 'mengirim'
        # -------------------------------------------------------------
        cur.execute(
            """
            UPDATE antrian_pesan
            SET status = 'mengirim', attempt_count = attempt_count + 1
            WHERE id = %s AND status = 'disetujui'
            """,
            (pesan_id,),
        )
        conn.commit()
        if cur.rowcount == 0:
            logger.info(f"Pesan ID {pesan_id} dilewati (sudah diambil worker lain).")
            continue

        # -------------------------------------------------------------
        # 2. Cek integritas: Apakah ada kasus terkait yang sudah 'selesai' di sela waktu?
        # -------------------------------------------------------------
        cur.execute(
            """
            SELECT COUNT(*) AS total_selesai
            FROM antrian_pesan_kasus apk
            JOIN kasus k ON k.id = apk.kasus_id
            WHERE apk.pesan_id = %s AND k.status = 'selesai'
            """,
            (pesan_id,),
        )
        sudah_selesai = cur.fetchone()["total_selesai"]
        if sudah_selesai > 0:
            logger.warning(
                f"Pesan ID {pesan_id} dibatalkan karena {sudah_selesai} kasus terkait telah SELESAI!"
            )
            cur.execute(
                """
                UPDATE antrian_pesan
                SET status = 'ditolak', rejected_reason = 'Sebagian kasus terkait sudah selesai (data berubah)'
                WHERE id = %s
                """,
                (pesan_id,),
            )
            conn.commit()
            cancelled_count += 1
            continue

        # -------------------------------------------------------------
        # 3. Kirim ke WhatsApp via Evolution API
        # -------------------------------------------------------------
        mentions = json.loads(msg["mentions"]) if msg.get("mentions") else []
        logger.info(f"Mengirim pesan ID {pesan_id} ke target {msg['target_jid']}...")
        ok, msg_id, payload = wa_client.send_whatsapp_message(
            target_jid=msg["target_jid"],
            text=msg["pesan"],
            mentions=mentions,
        )

        if ok:
            cur.execute(
                """
                UPDATE antrian_pesan
                SET status = 'terkirim',
                    sent_at = CURRENT_TIMESTAMP,
                    evolution_message_id = %s,
                    response_payload = %s
                WHERE id = %s
                """,
                (msg_id, json.dumps(payload), pesan_id),
            )
            # Update kasus-kasus terkait menjadi status 'menunggu_pic'
            cur.execute(
                """
                UPDATE kasus k
                JOIN antrian_pesan_kasus apk ON apk.kasus_id = k.id
                SET k.status = 'menunggu_pic', k.assigned_agent = 'Collector'
                WHERE apk.pesan_id = %s
                """,
                (pesan_id,),
            )
            sent_count += 1
            conn.commit()
            logger.info(f"✓ Pesan ID {pesan_id} sukses terkirim.")
        else:
            cur.execute(
                """
                UPDATE antrian_pesan
                SET status = 'gagal',
                    response_payload = %s
                WHERE id = %s
                """,
                (json.dumps(payload), pesan_id),
            )
            conn.commit()
            logger.error(f"✗ Pesan ID {pesan_id} gagal terkirim.")

        # Rate-limiting: Beri jeda acak 15 - 30 detik antar pesan keluar
        delay = random.randint(15, 30)
        time.sleep(delay)

    cur.close()
    conn.close()

    return {
        "status": "success",
        "total_sent": sent_count,
        "total_cancelled": cancelled_count,
    }

def main():
    run_id = db.start_agent_run("WA_Worker", pemicu="jadwal")
    try:
        res = process_approved_queue(run_id)
        db.finish_agent_run(run_id, status="selesai", detail=res)
        return res
    except Exception as e:
        db.finish_agent_run(run_id, status="gagal", error=str(e))
        raise

if __name__ == "__main__":
    run_job(main)
