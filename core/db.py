import json
from typing import Optional, Any
import mysql.connector
from mysql.connector import MySQLConnection
from core import config
from core.jobio import logger

def get_connection(database: Optional[str] = None) -> MySQLConnection:
    """Membuka koneksi ke MySQL."""
    db = database or config.DB_NAME
    conn = mysql.connector.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=db,
        charset="utf8mb4",
        collation="utf8mb4_unicode_ci",
    )
    # Pastikan timezone WIB (+07:00) agar CURDATE() dan DATEDIFF presisi
    cursor = conn.cursor()
    cursor.execute("SET time_zone = '+07:00';")
    cursor.close()
    return conn

def start_agent_run(agent_name: str, pemicu: str = "jadwal", model: Optional[str] = None) -> int:
    """Mencatat dimulainya run agent dan return agent_run.id."""
    conn = get_connection(config.DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO agent_run (agent_name, pemicu, model, status, mulai_at)
        VALUES (%s, %s, %s, 'berjalan', CURRENT_TIMESTAMP)
        """,
        (agent_name, pemicu, model),
    )
    run_id = cur.lastrowid
    conn.commit()
    cur.close()
    conn.close()
    return run_id

def finish_agent_run(
    run_id: int,
    status: str = "selesai",
    jumlah_iterasi: int = 0,
    token_input: int = 0,
    token_output: int = 0,
    error: Optional[str] = None,
    detail: Optional[dict[str, Any]] = None,
) -> None:
    """Mengupdate status akhir agent_run."""
    conn = get_connection(config.DB_NAME)
    cur = conn.cursor()
    detail_json = json.dumps(detail) if detail else None
    cur.execute(
        """
        UPDATE agent_run
        SET status = %s,
            jumlah_iterasi = %s,
            token_input = %s,
            token_output = %s,
            error = %s,
            detail = %s,
            selesai_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (status, jumlah_iterasi, token_input, token_output, error, detail_json, run_id),
    )
    conn.commit()
    cur.close()
    conn.close()

def log_riwayat(
    kasus_id: int,
    tindakan: str,
    actor_type: str = "system",
    actor_name: str = "sync_kasus",
    status_sebelum: Optional[str] = None,
    status_sesudah: Optional[str] = None,
    detail: Optional[dict[str, Any]] = None,
    catatan: Optional[str] = None,
    run_id: Optional[int] = None,
    conn: Optional[MySQLConnection] = None,
) -> None:
    """Mencatat entri ke tabel riwayat_tindakan."""
    should_close = False
    if conn is None:
        conn = get_connection(config.DB_NAME)
        should_close = True

    cur = conn.cursor()
    detail_json = json.dumps(detail) if detail else None
    cur.execute(
        """
        INSERT INTO riwayat_tindakan (
            kasus_id, run_id, actor_type, actor_name, tindakan,
            status_sebelum, status_sesudah, detail, catatan
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            kasus_id,
            run_id,
            actor_type,
            actor_name,
            tindakan,
            status_sebelum,
            status_sesudah,
            detail_json,
            catatan,
        ),
    )
    if should_close:
        conn.commit()
        cur.close()
        conn.close()
    else:
        cur.close()

if __name__ == "__main__":
    import sys
    logger.info("Testing MySQL Database Connection...")
    try:
        conn1 = get_connection(config.DB_NAME)
        logger.info(f"✓ Berhasil connect ke DB Target: {config.DB_NAME}")
        conn1.close()
    except Exception as e:
        logger.error(f"✗ Gagal connect ke DB Target ({config.DB_NAME}): {e}")

    try:
        conn2 = get_connection(config.DB_SOURCE_NAME)
        logger.info(f"✓ Berhasil connect ke DB Source: {config.DB_SOURCE_NAME}")
        conn2.close()
    except Exception as e:
        logger.error(f"✗ Gagal connect ke DB Source ({config.DB_SOURCE_NAME}): {e}")
