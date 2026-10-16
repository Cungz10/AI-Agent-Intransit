-- =====================================================================
-- Skema Database v2: Tim AI Agent Kiriman & Intransit
-- Target: MySQL 8.0+ / MariaDB 10.5+ | InnoDB | utf8mb4_unicode_ci
--
-- Perubahan dari v1:
--  1. kasus.kode_item NOT NULL DEFAULT ''  -> unique key tidak bolong lagi gara-gara NULL
--  2. antrian_pesan: status 'mengirim' (kunci anti kirim dobel), attempt_count,
--     dan guard maksimal 1 pesan aktif per kasus per jenis_pesan
--  3. kasus.umur_hari dibuang -> umur dihitung dari tgl_dokumen lewat view
--  4. FK audit trail pakai RESTRICT -> riwayat tidak ikut hilang
--  5. master_pic.urutan_kontak (1 = PIC utama); kasus.pic_id (FK) gantiin salinan nama/nomor
--  6. qty jadi DECIMAL(12,3) (aman buat barang timbangan)
--  7. Tambahan: tabel agent_run (jejak iterasi/token) + 3 view buat Manager
--
-- Ini FRESH INSTALL. Kalau v1 sudah ke-create dan belum ada data berharga:
--   DROP DATABASE intransit_agent;
--
-- Set timezone koneksi aplikasi/agent ke WIB supaya CURDATE() & DATEDIFF akurat:
--   SET time_zone = '+07:00';
-- =====================================================================

CREATE DATABASE IF NOT EXISTS `intransit_agent`
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE `intransit_agent`;

-- ---------------------------------------------------------------------
-- 1. Master PIC & Toko
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `master_pic` (
    `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `kode_toko` VARCHAR(20) NOT NULL,
    `nama_toko` VARCHAR(100) NOT NULL,
    `nama_pic` VARCHAR(100) NOT NULL,
    `nomor_wa` VARCHAR(30) NOT NULL COMMENT 'Format internasional, contoh: 6281234567890',
    `jabatan` VARCHAR(50) DEFAULT 'Kepala Toko' COMMENT 'Kepala Toko / Asisten / Adm / Korlap',
    `urutan_kontak` TINYINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '1 = dihubungi pertama (PIC utama), 2 = cadangan, dst',
    `is_aktif` TINYINT(1) NOT NULL DEFAULT 1,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY `uq_toko_pic` (`kode_toko`, `nomor_wa`),
    INDEX `idx_toko_urutan` (`kode_toko`, `is_aktif`, `urutan_kontak`),
    INDEX `idx_nomor_wa` (`nomor_wa`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 2. Agent Run (jejak eksekusi agent: iterasi, token, status)
--    Dipakai buat guardrail: max iterasi & budget token harian.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `agent_run` (
    `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `agent_name` VARCHAR(50) NOT NULL COMMENT 'Analis NRB, Rekap BA, Collector, Manager',
    `pemicu` ENUM('jadwal', 'manual', 'event') NOT NULL DEFAULT 'jadwal',
    `model` VARCHAR(50) NULL,
    `status` ENUM('berjalan', 'selesai', 'gagal', 'dihentikan_batas') NOT NULL DEFAULT 'berjalan'
        COMMENT 'dihentikan_batas = kena limit iterasi/token',
    `jumlah_iterasi` INT UNSIGNED NOT NULL DEFAULT 0,
    `token_input` BIGINT UNSIGNED NOT NULL DEFAULT 0,
    `token_output` BIGINT UNSIGNED NOT NULL DEFAULT 0,
    `error` TEXT NULL,
    `detail` JSON NULL,
    `mulai_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `selesai_at` TIMESTAMP NULL DEFAULT NULL,
    INDEX `idx_agent_mulai` (`agent_name`, `mulai_at`),
    INDEX `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 3. Kasus (Single Source of Truth)
--    Grain: satu baris per dokumen + item. Rekap per dokumen lewat view.
--    JANGAN di-DELETE. Kasus beres = status 'selesai'.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `kasus` (
    `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `jenis` ENUM('NRB', 'BA_KURANG', 'INTRANSIT', 'BPB', 'LAINNYA') NOT NULL,
    `kode_toko` VARCHAR(20) NOT NULL,
    `nama_toko` VARCHAR(100) NULL,
    `docno` VARCHAR(50) NOT NULL COMMENT 'No dokumen / No Surat Jalan / No NRB / No BPB',
    `kode_item` VARCHAR(50) NOT NULL DEFAULT '' COMMENT 'PLU/barcode. Kosong ('''') kalau kasus level dokumen. Sengaja NOT NULL supaya unique key bekerja',
    `nama_item` VARCHAR(255) NULL,
    `qty` DECIMAL(12, 3) NOT NULL DEFAULT 0.000 COMMENT 'Selisih kuantitas fisik vs dokumen',
    `nilai` DECIMAL(15, 2) NOT NULL DEFAULT 0.00 COMMENT 'Nilai selisih (Rp)',
    `tgl_dokumen` DATE NULL COMMENT 'Tanggal dokumen/kiriman. Dasar hitung umur kasus. Kalau NULL, view pakai tanggal created_at',
    `status` ENUM('baru', 'diproses', 'menunggu_pic', 'selesai', 'eskalasi') NOT NULL DEFAULT 'baru',
    `prioritas` ENUM('rendah', 'sedang', 'tinggi', 'urgent') NOT NULL DEFAULT 'sedang',
    `pic_id` BIGINT UNSIGNED NULL COMMENT 'PIC yang ditugaskan; kalau NULL Collector pakai PIC utama toko',
    `sumber` VARCHAR(100) NOT NULL COMMENT 'Nama file/script asal (e.g., nrb_vs_alokasi.py)',
    `catatan` TEXT NULL COMMENT 'Dugaan penyebab / ringkasan reasoning dari agent',
    `assigned_agent` VARCHAR(50) NULL COMMENT 'Agent yang sedang memegang kasus',
    `resolved_at` TIMESTAMP NULL DEFAULT NULL,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT `fk_kasus_pic` FOREIGN KEY (`pic_id`) REFERENCES `master_pic` (`id`) ON DELETE SET NULL,
    UNIQUE KEY `uq_kasus_unik` (`jenis`, `docno`, `kode_toko`, `kode_item`),
    INDEX `idx_status_prioritas` (`status`, `prioritas`),
    INDEX `idx_kode_toko` (`kode_toko`),
    INDEX `idx_docno` (`docno`),
    INDEX `idx_nilai` (`nilai`),
    INDEX `idx_tgl_dokumen` (`tgl_dokumen`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 4. Antrian Pesan (Outbox WA + approval)
--    Alur status:
--      draft              : Collector masih nyusun
--      menunggu_approval  : siap direview manusia
--      disetujui          : sudah di-approve, belum diambil worker
--      mengirim           : sudah "dikunci" worker, lagi dikirim (anti dobel)
--      terkirim / gagal   : hasil akhir
--      ditolak            : ditolak manusia / batal
--    Satu pesan = satu dokumen: kasus_id diisi kasus perwakilan (mis. item pertama).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `antrian_pesan` (
    `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `kasus_id` BIGINT UNSIGNED NOT NULL,
    `nomor_tujuan` VARCHAR(30) NOT NULL COMMENT 'Snapshot nomor WA saat pesan dibuat (format 628xxx)',
    `nama_penerima` VARCHAR(100) NULL,
    `jenis_pesan` ENUM('tagihan_awal', 'follow_up', 'konfirmasi_selesai', 'eskalasi', 'custom') NOT NULL DEFAULT 'tagihan_awal',
    `template_id` VARCHAR(50) NULL,
    `pesan` TEXT NOT NULL COMMENT 'Isi draft pesan WhatsApp dari Collector',
    `status` ENUM('draft', 'menunggu_approval', 'disetujui', 'mengirim', 'ditolak', 'terkirim', 'gagal')
        NOT NULL DEFAULT 'menunggu_approval',
    `aktif_key` TINYINT GENERATED ALWAYS AS (
        IF(`status` IN ('draft', 'menunggu_approval', 'disetujui', 'mengirim'), 1, NULL)
    ) STORED COMMENT 'Otomatis. 1 selama pesan masih aktif; dipakai unique key anti pesan ganda',
    `approved_by` VARCHAR(50) NULL,
    `approved_at` TIMESTAMP NULL DEFAULT NULL,
    `rejected_reason` VARCHAR(255) NULL,
    `scheduled_at` TIMESTAMP NULL DEFAULT NULL COMMENT 'Jadwal kirim (rate-limit & anti-spam)',
    `attempt_count` TINYINT UNSIGNED NOT NULL DEFAULT 0,
    `sent_at` TIMESTAMP NULL DEFAULT NULL,
    `evolution_message_id` VARCHAR(100) NULL,
    `response_payload` JSON NULL COMMENT 'Raw respons dari WhatsApp gateway',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT `fk_antrian_kasus` FOREIGN KEY (`kasus_id`) REFERENCES `kasus` (`id`) ON DELETE RESTRICT,
    -- maksimal 1 pesan aktif per kasus per jenis_pesan (NULL tidak dihitung, jadi riwayat lama aman)
    UNIQUE KEY `uq_pesan_aktif` (`kasus_id`, `jenis_pesan`, `aktif_key`),
    INDEX `idx_status_scheduled` (`status`, `scheduled_at`),
    INDEX `idx_nomor_tujuan` (`nomor_tujuan`, `sent_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 5. Riwayat Tindakan (Audit Trail)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `riwayat_tindakan` (
    `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `kasus_id` BIGINT UNSIGNED NOT NULL,
    `run_id` BIGINT UNSIGNED NULL COMMENT 'agent_run yang melakukan tindakan (kalau oleh agent)',
    `actor_type` ENUM('agent', 'human', 'system', 'pic') NOT NULL,
    `actor_name` VARCHAR(50) NOT NULL,
    `tindakan` VARCHAR(50) NOT NULL COMMENT 'analisis_selisih, draft_pesan, approve_pesan, kirim_wa, terima_balasan, update_status, eskalasi',
    `status_sebelum` VARCHAR(50) NULL,
    `status_sesudah` VARCHAR(50) NULL,
    `detail` JSON NULL,
    `catatan` TEXT NULL,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT `fk_riwayat_kasus` FOREIGN KEY (`kasus_id`) REFERENCES `kasus` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_riwayat_run` FOREIGN KEY (`run_id`) REFERENCES `agent_run` (`id`) ON DELETE SET NULL,
    INDEX `idx_kasus_tindakan` (`kasus_id`, `created_at`),
    INDEX `idx_actor` (`actor_type`, `actor_name`),
    INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================================
-- VIEW
-- Kalau kolom tabel kasus berubah, jalankan ulang CREATE OR REPLACE VIEW.
-- =====================================================================

-- A. Kasus terbuka level item, lengkap dengan umur (hari)
CREATE OR REPLACE VIEW `v_kasus_aktif` AS
SELECT
    k.*,
    DATEDIFF(CURDATE(), COALESCE(k.tgl_dokumen, DATE(k.created_at))) AS umur_hari
FROM `kasus` k
WHERE k.status <> 'selesai';

-- B. Rekap kasus terbuka per dokumen (item di-SUM)
CREATE OR REPLACE VIEW `v_kasus_dokumen` AS
SELECT
    k.jenis,
    k.kode_toko,
    MAX(k.nama_toko) AS nama_toko,
    k.docno,
    COUNT(*) AS jumlah_item,
    SUM(k.qty) AS total_qty,
    SUM(k.nilai) AS total_nilai,
    MIN(COALESCE(k.tgl_dokumen, DATE(k.created_at))) AS tgl_dokumen,
    DATEDIFF(CURDATE(), MIN(COALESCE(k.tgl_dokumen, DATE(k.created_at)))) AS umur_hari,
    MAX(FIELD(k.prioritas, 'rendah', 'sedang', 'tinggi', 'urgent')) AS level_prioritas, -- 1 rendah .. 4 urgent
    MAX(k.status = 'eskalasi') AS ada_eskalasi,
    MIN(k.id) AS kasus_id_perwakilan
FROM `kasus` k
WHERE k.status <> 'selesai'
GROUP BY k.jenis, k.kode_toko, k.docno;

-- C. Bahan baku Manager: dokumen terbuka + PIC utama + riwayat kontak + skor
--    skor_prioritas = ABS(nilai) x (1 + umur/30) -> formula awal, silakan ubah sesuai kebijakan.
CREATE OR REPLACE VIEW `v_antrian_manager` AS
SELECT
    d.*,
    p.id AS pic_id,
    p.nama_pic,
    p.nomor_wa AS nomor_pic,
    COALESCE(m.pesan_terkirim, 0) AS pesan_terkirim,
    m.terakhir_kirim,
    DATEDIFF(CURDATE(), DATE(m.terakhir_kirim)) AS hari_sejak_kontak,
    ROUND(ABS(d.total_nilai) * (1 + d.umur_hari / 30), 2) AS skor_prioritas
FROM `v_kasus_dokumen` d
LEFT JOIN `master_pic` p
    ON p.id = (
        SELECT p2.id
        FROM `master_pic` p2
        WHERE p2.kode_toko = d.kode_toko AND p2.is_aktif = 1
        ORDER BY p2.urutan_kontak, p2.id
        LIMIT 1
    )
LEFT JOIN (
    SELECT
        k.jenis, k.kode_toko, k.docno,
        COUNT(*) AS pesan_terkirim,
        MAX(a.sent_at) AS terakhir_kirim
    FROM `antrian_pesan` a
    JOIN `kasus` k ON k.id = a.kasus_id
    WHERE a.status = 'terkirim'
    GROUP BY k.jenis, k.kode_toko, k.docno
) m
    ON m.jenis = d.jenis AND m.kode_toko = d.kode_toko AND m.docno = d.docno;

-- =====================================================================
-- QUERY SIAP PAKAI (referensi buat script/agent, tidak dieksekusi)
-- =====================================================================

-- 1) Upsert dari script matching (aman di-rerun; status/catatan/prioritas TIDAK ditimpa)
-- INSERT INTO kasus (jenis, kode_toko, nama_toko, docno, kode_item, nama_item, qty, nilai, tgl_dokumen, sumber)
-- VALUES ('NRB', ?, ?, ?, ?, ?, ?, ?, ?, 'nrb_vs_alokasi.py')
-- ON DUPLICATE KEY UPDATE
--     nama_toko = VALUES(nama_toko), nama_item = VALUES(nama_item),
--     qty = VALUES(qty), nilai = VALUES(nilai), sumber = VALUES(sumber);

-- 2) Worker WA "klaim" pesan sebelum kirim (affected rows harus 1, kalau 0 -> SKIP)
--    Sekalian memastikan kasusnya belum selesai di antara approve dan kirim.
-- UPDATE antrian_pesan a
-- JOIN kasus k ON k.id = a.kasus_id
-- SET a.status = 'mengirim', a.attempt_count = a.attempt_count + 1
-- WHERE a.id = ? AND a.status = 'disetujui' AND k.status <> 'selesai';

-- 3) Cek jatah kirim PIC hari ini (rate limit, contoh batas 2 pesan/hari)
-- SELECT COUNT(*) FROM antrian_pesan
-- WHERE nomor_tujuan = ?
--   AND status IN ('disetujui', 'mengirim', 'terkirim')
--   AND DATE(COALESCE(sent_at, scheduled_at, created_at)) = CURDATE();

-- 4) Daftar prioritas harian buat Manager
-- SELECT * FROM v_antrian_manager ORDER BY skor_prioritas DESC LIMIT 20;

-- 5) Budget token harian per agent
-- SELECT agent_name, SUM(token_input + token_output) AS total_token
-- FROM agent_run WHERE mulai_at >= CURDATE() GROUP BY agent_name;