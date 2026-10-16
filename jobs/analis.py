from core import config, db, llm
from core.jobio import run_job, logger

SYSTEM_PROMPT = """
Anda adalah AI Analis Logistik & Inventory Kiriman Toko.
Tugas Anda:
1. Membaca data selisih fisik vs dokumen atau intransit macet.
2. Memberikan 'dugaan_penyebab' yang logis, tajam, dan singkat (maksimal 2 kalimat).
   - Jika indikasi_awal = 'plu_tidak_aktif', jelaskan bahwa kemungkinan besar toko gagal BPB karena master PLU tidak dikenali/tidak aktif di cabang.
   - Jika satu item selisih di banyak nota/toko sekaligus, curigai error program / sinkronisasi data.
   - Jika hanya 1 toko dengan nilai/qty ganjil, curigai potensi kurang fisik pengiriman atau belum ter-input.
3. Menentukan 'prioritas' ('rendah', 'sedang', 'tinggi', 'urgent') berdasarkan nilai uang dan umur hari.
4. Menyusun 1 'pertanyaan_klarifikasi' untuk ditanyakan kepada PIC cabang/toko.

PENTING:
- DILARANG mengubah angka qty atau nilai.
- Kembalikan HANYA format JSON valid dengan struktur:
{
  "analisis": [
    {
      "kasus_id": 123,
      "dugaan_penyebab": "string",
      "prioritas": "rendah|sedang|tinggi|urgent",
      "pertanyaan_klarifikasi": "string"
    }
  ]
}
"""

def proses_analisis_kasus(run_id: int, batch_size: int = 15) -> dict:
    conn = db.get_connection(config.DB_NAME)
    cur = conn.cursor(dictionary=True)

    # Ambil kasus berstatus baru yang belum ada catatan analisisnya
    cur.execute(
        """
        SELECT 
            k.id AS kasus_id,
            k.jenis,
            k.kode_cabang,
            k.kode_toko,
            k.nama_toko,
            k.docno,
            k.kode_item,
            k.nama_item,
            k.qty,
            k.nilai,
            k.tgl_dokumen,
            DATEDIFF(CURDATE(), COALESCE(k.tgl_dokumen, DATE(k.created_at))) AS umur_hari,
            k.indikasi_awal
        FROM kasus k
        WHERE k.status = 'baru' AND k.catatan IS NULL
        ORDER BY k.nilai DESC
        LIMIT %s
        """,
        (batch_size,),
    )
    kasus_list = cur.fetchall()

    if not kasus_list:
        logger.info("Tidak ada kasus baru yang memerlukan analisis LLM.")
        cur.close()
        conn.close()
        return {"status": "no_pending_cases", "processed": 0}

    logger.info(f"Mengirim {len(kasus_list)} kasus ke LLM (9router)...")
    user_prompt = f"Berikut adalah daftar kasus untuk dianalisis:\n{kasus_list}"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    parsed_res, token_in, token_out = llm.call_llm_json(
        messages=messages,
        model=config.LLM_MODEL_CHEAP,
        temperature=0.2,
    )

    analisis_items = parsed_res.get("analisis", [])
    logger.info(f"Menerima {len(analisis_items)} hasil analisis dari LLM (Token in: {token_in}, out: {token_out})")

    update_count = 0
    for item in analisis_items:
        k_id = item.get("kasus_id")
        dugaan = item.get("dugaan_penyebab")
        prioritas = item.get("prioritas", "sedang")
        klarif = item.get("pertanyaan_klarifikasi", "")
        catatan_gabung = f"{dugaan} [Klarifikasi: {klarif}]"

        cur.execute(
            """
            UPDATE kasus
            SET catatan = %s,
                prioritas = %s,
                status = 'diproses',
                assigned_agent = 'Analis'
            WHERE id = %s
            """,
            (catatan_gabung, prioritas, k_id),
        )

        db.log_riwayat(
            kasus_id=k_id,
            tindakan="analisis_selisih",
            actor_type="agent",
            actor_name="Analis",
            status_sebelum="baru",
            status_sesudah="diproses",
            catatan=catatan_gabung,
            run_id=run_id,
            conn=conn,
        )
        update_count += 1

    conn.commit()
    cur.close()
    conn.close()

    return {
        "status": "success",
        "processed": update_count,
        "token_input": token_in,
        "token_output": token_out,
    }

def main():
    run_id = db.start_agent_run("Analis", pemicu="jadwal", model=config.LLM_MODEL_CHEAP)
    try:
        res = proses_analisis_kasus(run_id)
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
