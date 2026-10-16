from core import config, db, llm
from core.jobio import run_job, logger

MANAGER_PROMPT = """
Anda adalah AI Operational Manager Logistik & Kiriman.
Tugas Anda:
1. Membaca ringkasan kasus antrian per cabang (total nilai, jumlah nota, umur tertua).
2. Menyusun ringkasan eksekutif pagi yang padat dan profesional untuk dikirim via WA ke Head of Logistics.
3. Menyebutkan Top 3 cabang yang paling kritis dan harus segera ditindaklanjuti Collector hari ini beserta alasannya.

Format Output HANYA JSON:
{
  "ringkasan_teks": "Selamat Pagi Pak... (teks WA rapi lengkap dengan bullet points)",
  "cabang_prioritas": ["G001", "G026", "G113"]
}
"""

def generate_manager_brief(run_id: int) -> dict:
    conn = db.get_connection(config.DB_NAME)
    cur = conn.cursor(dictionary=True)

    cur.execute(
        """
        SELECT * FROM v_antrian_manager
        ORDER BY skor_prioritas DESC
        """
    )
    cabang_summary = cur.fetchall()

    if not cabang_summary:
        logger.info("Tidak ada antrian kasus terbuka hari ini. Situasi aman.")
        cur.close()
        conn.close()
        return {"status": "no_active_cases", "message": "Semua kasus beres."}

    logger.info("Menyusun ringkasan eksekutif via LLM Smart (9router)...")
    messages = [
        {"role": "system", "content": MANAGER_PROMPT},
        {
            "role": "user",
            "content": f"Data antrian cabang hari ini:\n{cabang_summary}",
        },
    ]

    res, token_in, token_out = llm.call_llm_json(
        messages=messages,
        model=config.LLM_MODEL_SMART,
        temperature=0.3,
    )

    ringkasan_teks = res.get("ringkasan_teks", "")
    cabang_prioritas = res.get("cabang_prioritas", [])

    # Naikkan prioritas kasus di cabang terpilih
    if cabang_prioritas:
        format_strings = ",".join(["%s"] * len(cabang_prioritas))
        cur.execute(
            f"""
            UPDATE kasus
            SET prioritas = 'urgent'
            WHERE kode_cabang IN ({format_strings}) AND status <> 'selesai'
            """,
            tuple(cabang_prioritas),
        )
        conn.commit()

    cur.close()
    conn.close()

    return {
        "status": "success",
        "ringkasan_teks": ringkasan_teks,
        "cabang_prioritas": cabang_prioritas,
        "token_input": token_in,
        "token_output": token_out,
    }

def main():
    run_id = db.start_agent_run("Manager", pemicu="jadwal", model=config.LLM_MODEL_SMART)
    try:
        res = generate_manager_brief(run_id)
        db.finish_agent_run(
            run_id,
            status="selesai",
            token_input=res.get("token_input", 0),
            token_output=res.get("token_output", 0),
            detail=res,
        )
        return res
    except Exception as e:
        db.finish_agent_run(run_id, status="gagal", error=str(e))
        raise

if __name__ == "__main__":
    run_job(main)
