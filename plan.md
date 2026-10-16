# Plan: Tim AI Agent Kiriman & Intransit

## 1. Tujuan

Bikin tim AI agent yang bantu ngurusin kiriman dan intransit: dari analisis selisih, rekap berita acara (BA) kurang, nagih PIC lewat WA, sampai nyusun prioritas harian.

**Target akhir:** pagi buka laporan, udah tau kasus mana yang harus diurus duluan, dan draft pesan ke PIC udah siap tinggal approve.

## 2. Prinsip Utama

1. **LLM tidak boleh ngitung/matching angka.** Semua logic deterministik (NRB vs alokasi, BPB vs intransit, flatten rekap BK) tetap di script Python/PHP. Agent cuma *manggil* script sebagai tool.
2. **LLM ngurus judgment dan komunikasi:** baca hasil, nentuin prioritas, nulis pesan, ngerangkum.
3. **Satu sumber kebenaran:** semua agent baca/tulis ke tabel `kasus` di MySQL, bukan ngobrol teks bebas.
4. **Human-in-the-loop dulu:** semua pesan keluar (WA) lewat approval sampai sistemnya terbukti aman.
5. **Bangun bertahap:** jangan langsung 5 agent.

## 3. Arsitektur

```
[Trigger/Jadwal: n8n]
        |
        v
[Orchestrator: Hermes / n8n]
        |
  +-----+------+-----------+-----------+
  |            |           |           |
Analis NRB   Rekap BA    Collector   Manager
  |            |           |           |
  +------------+-----+-----+-----------+
                     |
              [MySQL: tabel kasus]
                     |
         [Tools: script matching, Evolution API WA]
```

## 4. Peran Agent

| Agent | Tugas | Tool | Output |
|---|---|---|---|
| **Analis NRB/Retur** | Jalanin matching, cari selisih, kasih dugaan penyebab | Script NRB vs Alokasi, BPB vs Intransit | Baris baru/update di tabel `kasus` |
| **Rekap BA Kurang** | Kumpulin & flatten data BA, cocokin ke intransit | Script flatten rekap BK | Daftar kasus terbuka |
| **Collector** | Susun draft WA ke PIC, catat balasan, follow-up | Evolution API (WA) | Draft pesan, log komunikasi |
| **Manager** | Baca semua kasus, prioritasin (nilai terbesar, umur terlama), kasih instruksi ke collector | Query tabel `kasus` | Daftar prioritas harian |

**Pilihan model:** Manager pakai model pinter, agent lain pakai model murah (hemat token).

## 5. Skema Tabel `kasus` (draft awal)

| Kolom | Keterangan |
|---|---|
| `id` | PK |
| `jenis` | NRB / BA kurang / intransit / BPB |
| `toko` | Kode & nama toko |
| `docno` | No dokumen / surat jalan |
| `nilai` | Nilai selisih (Rp) |
| `qty` | Qty selisih |
| `status` | baru / diproses / menunggu_pic / selesai / eskalasi |
| `umur_hari` | Umur kasus |
| `pic` | PIC yang dihubungi |
| `sumber` | Script/laporan asal |
| `catatan` | Dugaan penyebab / hasil analisis |
| `created_at`, `updated_at` | Timestamp |

Tabel pendukung: `riwayat_tindakan` (log semua aksi agent), `antrian_pesan` (draft WA + status approval).

## 6. Tahapan Pembangunan

### Fase 1: Fondasi
- [x] Rancang & buat tabel `kasus`, `riwayat_tindakan`, `antrian_pesan` (lihat [schema.sql](file:///c:/Users/YC_CBN_CAD/intransit-agent/schema.sql))
- [ ] Bungkus script yang sudah ada jadi tool (API sederhana / CLI dengan output JSON)
- [ ] Pastikan output script konsisten dan bisa ditulis ke tabel `kasus`

**Selesai kalau:** jalanin satu script, hasilnya masuk tabel `kasus` otomatis.

### Fase 2: Agent Analis
- [ ] Agent Analis NRB/Retur manggil script, isi tabel `kasus`
- [ ] Agent Rekap BA Kurang ngisi kasus terbuka
- [ ] Tambah dugaan penyebab (judgment LLM, angka tetap dari script)
- [ ] Validasi hasil vs perhitungan manual untuk beberapa sampel

**Selesai kalau:** hasil agent cocok sama hitungan manual di sampel uji.

### Fase 3: Collector (Mode Draft)
- [ ] Template pesan per jenis kasus
- [ ] Agent bikin draft WA, masuk `antrian_pesan` dengan status `menunggu_approval`
- [ ] UI/command sederhana buat approve/tolak (bisa lewat WA ke diri sendiri atau halaman web kecil)
- [ ] Setelah approve, kirim lewat Evolution API
- [ ] Catat balasan PIC ke `riwayat_tindakan`

**Selesai kalau:** alur draft → approve → kirim → catat balasan jalan mulus.

### Fase 4: Manager
- [ ] Agent Manager baca tabel `kasus`, susun prioritas harian
- [ ] Output: ringkasan pagi (top kasus, total nilai terbuka, kasus yang mandek)
- [ ] Manager kasih instruksi ke Collector (siapa ditagih duluan)

**Selesai kalau:** ringkasan harian akurat dan berguna tanpa perlu dikoreksi tiap hari.

### Fase 5: Otomasi Lebih Jauh (Opsional)
- [ ] Longgarkan approval untuk jenis pesan yang low-risk
- [ ] Dashboard visual status agent (Vue + websocket), kalau masih semangat

## 7. Guardrail & Risiko

| Risiko | Mitigasi |
|---|---|
| Salah kirim / nagih kasus yang sudah beres | Mode draft + cek status kasus sebelum kirim |
| Nomor WA kena banned | Batas pesan per hari per PIC, jeda antar pesan, jangan blast |
| LLM ngarang angka | Angka hanya dari script, LLM dilarang ngitung |
| Agent muter-muter / boros token | Max iterasi, timeout, budget token harian |
| Data sensitif bocor ke prompt | Kirim ke LLM hanya kolom yang perlu |
| Sulit audit kalau ada kesalahan | Log semua aksi agent di `riwayat_tindakan` |
| Agent saling tabrakan nulis data | Tiap agent punya "kepemilikan" kolom/status tertentu |

**Aturan batas wajib:**
- Max pesan per PIC per hari: tentukan (misal 2)
- Max iterasi per run agent: tentukan
- Semua aksi tercatat dengan timestamp dan agent pelaku

## 8. Tech Stack

- **Database:** MySQL
- **Script/tool:** Python / PHP (yang sudah ada)
- **Orchestrator:** n8n (jadwal & trigger) + Hermes (agent fleksibel)
- **WA:** Evolution API
- **Model:** model pinter untuk Manager, model murah untuk lainnya
- **Dashboard (opsional):** Laravel + Vue

## 9. Metrik Keberhasilan

- Waktu nyusun rekap harian turun (bandingkan sebelum vs sesudah)
- Akurasi hasil agent vs hitungan manual (target: 100% di angka)
- Jumlah kasus yang ke-follow-up tepat waktu
- Rata-rata umur kasus terbuka turun
- Jumlah koreksi manual terhadap draft Collector (makin sedikit makin bagus)

## 10. Pertanyaan Terbuka

- [ ] Kasus yang paling makan waktu: nyari data atau nagih PIC? (nentuin agent mana didahulukan)
- [ ] Siapa aja PIC dan gimana datanya disimpan (nomor WA, toko yang dipegang)?
- [ ] Batas kebijakan eskalasi: kasus umur berapa hari naik ke atasan?
- [ ] Hermes atau n8n yang jadi orchestrator utama?
- [ ] Format approval yang paling nyaman buat lu (WA, web, atau CLI)?

## 11. Langkah Pertama (Minggu Ini)

1. Putuskan skema final tabel `kasus`
2. Pilih **satu** script (misal NRB vs Alokasi) dan bungkus jadi tool dengan output JSON
3. Bikin agent Analis paling sederhana yang manggil tool itu dan nulis ke `kasus`
4. Cek hasilnya vs hitungan manual
