-- =====================================================================
-- Skema Database v3: Tim AI Agent Kiriman & Intransit
-- Target: MySQL 8.0+ / MariaDB 10.5+ | InnoDB | utf8mb4_unicode_ci
--
-- Perubahan di v3:
--  1. Tambah master_cabang & sesuaikan master_pic per cabang (bukan per toko).
--  2. kasus: tambah kode_cabang, terakhir_terlihat, indikasi_awal, hasil_klarifikasi.
--     jenis tambah 'SELISIH_BK'.
--  3. antrian_pesan: pesan berbasis cabang/grup gabungan (antrian_pesan_kasus).
--  4. Tambah tabel snapshot_intransit (penentu auto-close & reopen).
--  5. Tambah ref_plu (lookup PLU aktif / IDM).
-- =====================================================================

CREATE DATABASE IF NOT EXISTS `intransit_agent`
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE `intransit_agent`;

-- ---------------------------------------------------------------------
-- 1. Master Cabang & Master PIC
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `master_cabang` (
    `kode_cabang` VARCHAR(10) PRIMARY KEY COMMENT 'Contoh: G001, G026',
    `nama_cabang` VARCHAR(100) NOT NULL COMMENT 'Contoh: Jakarta 1 (G001)',
    `is_aktif` TINYINT(1) NOT NULL DEFAULT 1,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `master_pic` (
    `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `kode_cabang` VARCHAR(10) NOT NULL,
    `nama_pic` VARCHAR(100) NOT NULL,
    `nomor_wa` VARCHAR(50) NOT NULL COMMENT 'Format internasional, contoh: 6281234567890',
    `jabatan` VARCHAR(50) DEFAULT 'Korlap / PIC Cabang',
    `urutan_kontak` TINYINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '1 = PIC utama (akan di-mention), 2 = cadangan',
    `is_aktif` TINYINT(1) NOT NULL DEFAULT 1,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT `fk_pic_cabang` FOREIGN KEY (`kode_cabang`) REFERENCES `master_cabang` (`kode_cabang`) ON DELETE CASCADE,
    UNIQUE KEY `uq_cabang_pic` (`kode_cabang`, `nomor_wa`),
    INDEX `idx_cabang_urutan` (`kode_cabang`, `is_aktif`, `urutan_kontak`),
    INDEX `idx_nomor_wa` (`nomor_wa`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 2. Agent Run (Audit Execution, Guardrail Token & Iterasi)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `agent_run` (
    `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `agent_name` VARCHAR(50) NOT NULL COMMENT 'Analis, Collector, Manager, Sync',
    `pemicu` ENUM('jadwal', 'manual', 'event') NOT NULL DEFAULT 'jadwal',
    `model` VARCHAR(50) NULL,
    `status` ENUM('berjalan', 'selesai', 'gagal', 'dihentikan_batas') NOT NULL DEFAULT 'berjalan',
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
-- 3. Snapshot Intransit (Hasil Download Rekap Kumulatif H-1)
--    Sebagai pembanding eksistensi kasus untuk Auto-Close / Reopen.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `snapshot_intransit` (
    `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `tgl_snapshot` DATE NOT NULL,
    `jenis_masalah` VARCHAR(30) NOT NULL,
    `kode_cabang` VARCHAR(10) NOT NULL,
    `kode_toko` VARCHAR(20) NOT NULL,
    `nama_toko` VARCHAR(100) NULL,
    `docno` VARCHAR(50) NOT NULL,
    `tgl_kirim` DATE NULL,
    `nilai_sj` DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    `nama_item_selisih` TEXT NULL,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY `uq_snap` (`tgl_snapshot`, `jenis_masalah`, `kode_toko`, `docno`),
    INDEX `idx_snap_doc` (`docno`, `tgl_snapshot`),
    INDEX `idx_snap_cabang` (`kode_cabang`, `tgl_snapshot`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 4. Referensi PLU (Mapping Master PriceList IDM)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `ref_plu` (
    `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `kode_fg` VARCHAR(50) NOT NULL,
    `nama_item` VARCHAR(255) NULL,
    `conv_channel` VARCHAR(50) NOT NULL DEFAULT 'IDM',
    `plu_idm` VARCHAR(50) NOT NULL DEFAULT '0',
    `is_aktif` TINYINT(1) NOT NULL DEFAULT 1,
    `tgl_sync` DATE NOT NULL,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY `uq_fg_channel` (`kode_fg`, `conv_channel`),
    INDEX `idx_plu_idm` (`plu_idm`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 5. Kasus (Single Source of Truth)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `kasus` (
    `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `jenis` ENUM('NRB', 'BA_KURANG', 'INTRANSIT', 'SELISIH_BK', 'BPB', 'LAINNYA') NOT NULL,
    `kode_cabang` VARCHAR(10) NOT NULL,
    `kode_toko` VARCHAR(20) NOT NULL,
    `nama_toko` VARCHAR(100) NULL,
    `docno` VARCHAR(50) NOT NULL COMMENT 'No Nota / No Surat Jalan',
    `kode_item` VARCHAR(50) NOT NULL DEFAULT '' COMMENT 'Kode FG / PLU item',
    `nama_item` VARCHAR(255) NULL,
    `qty` DECIMAL(12, 3) NOT NULL DEFAULT 0.000 COMMENT 'Selisih kuantitas',
    `nilai` DECIMAL(15, 2) NOT NULL DEFAULT 0.00 COMMENT 'Nilai selisih (Rp)',
    `tgl_dokumen` DATE NULL COMMENT 'Tanggal kirim / dokumen',
    `terakhir_terlihat` DATE NULL COMMENT 'Tgl snapshot terakhir nota ini masih ada',
    `status` ENUM('baru', 'diproses', 'menunggu_pic', 'selesai', 'eskalasi') NOT NULL DEFAULT 'baru',
    `prioritas` ENUM('rendah', 'sedang', 'tinggi', 'urgent') NOT NULL DEFAULT 'sedang',
    `indikasi_awal` ENUM('plu_tidak_aktif', 'tidak_diketahui') NOT NULL DEFAULT 'tidak_diketahui',
    `hasil_klarifikasi` ENUM('kurang_fisik', 'plu_tidak_aktif', 'error_program', 'lainnya') NULL,
    `sumber` VARCHAR(100) NOT NULL COMMENT 'Nama tabel/script asal (e.g., rekap_selisih_bk)',
    `catatan` TEXT NULL COMMENT 'Dugaan penyebab / ringkasan reasoning dari agent',
    `assigned_agent` VARCHAR(50) NULL,
    `resolved_at` TIMESTAMP NULL DEFAULT NULL,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT `fk_kasus_cabang` FOREIGN KEY (`kode_cabang`) REFERENCES `master_cabang` (`kode_cabang`),
    UNIQUE KEY `uq_kasus_unik` (`jenis`, `docno`, `kode_toko`, `kode_item`),
    INDEX `idx_cabang_status` (`kode_cabang`, `status`),
    INDEX `idx_status_prioritas` (`status`, `prioritas`),
    INDEX `idx_kode_toko` (`kode_toko`),
    INDEX `idx_docno` (`docno`),
    INDEX `idx_nilai` (`nilai`),
    INDEX `idx_tgl_dokumen` (`tgl_dokumen`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 6. Antrian Pesan & Relasi Kasus
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `antrian_pesan` (
    `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `kode_cabang` VARCHAR(10) NULL COMMENT 'NULL jika pesan gabungan multi cabang',
    `target_jid` VARCHAR(100) NOT NULL COMMENT 'Grup WA JID atau nomor tujuan',
    `mentions` JSON NULL COMMENT 'Array nomor WA PIC yang di-tag [@628xxx]',
    `jenis_pesan` ENUM('tagihan_awal', 'follow_up', 'klarifikasi_selisih', 'konfirmasi_selesai', 'eskalasi', 'custom') NOT NULL DEFAULT 'tagihan_awal',
    `template_id` VARCHAR(50) NULL,
    `pesan` TEXT NOT NULL COMMENT 'Draft isi pesan WhatsApp',
    `status` ENUM('draft', 'menunggu_approval', 'disetujui', 'mengirim', 'ditolak', 'terkirim', 'gagal')
        NOT NULL DEFAULT 'menunggu_approval',
    `aktif_key` TINYINT GENERATED ALWAYS AS (
        IF(`status` IN ('draft', 'menunggu_approval', 'disetujui', 'mengirim'), 1, NULL)
    ) STORED COMMENT 'Otomatis: 1 selama masih aktif, mencegah draft ganda',
    `approved_by` VARCHAR(50) NULL,
    `approved_at` TIMESTAMP NULL DEFAULT NULL,
    `rejected_reason` VARCHAR(255) NULL,
    `scheduled_at` TIMESTAMP NULL DEFAULT NULL,
    `attempt_count` TINYINT UNSIGNED NOT NULL DEFAULT 0,
    `sent_at` TIMESTAMP NULL DEFAULT NULL,
    `evolution_message_id` VARCHAR(100) NULL,
    `response_payload` JSON NULL,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX `idx_status_scheduled` (`status`, `scheduled_at`),
    INDEX `idx_target_jid` (`target_jid`, `sent_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `antrian_pesan_kasus` (
    `pesan_id` BIGINT UNSIGNED NOT NULL,
    `kasus_id` BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (`pesan_id`, `kasus_id`),
    CONSTRAINT `fk_apk_pesan` FOREIGN KEY (`pesan_id`) REFERENCES `antrian_pesan` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_apk_kasus` FOREIGN KEY (`kasus_id`) REFERENCES `kasus` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 7. Riwayat Tindakan (Audit Trail)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `riwayat_tindakan` (
    `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    `kasus_id` BIGINT UNSIGNED NOT NULL,
    `run_id` BIGINT UNSIGNED NULL,
    `actor_type` ENUM('agent', 'human', 'system', 'pic') NOT NULL,
    `actor_name` VARCHAR(50) NOT NULL,
    `tindakan` VARCHAR(50) NOT NULL COMMENT 'sync, analisis_selisih, draft_pesan, approve_pesan, kirim_wa, terima_balasan, update_status, auto_close, reopen',
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
-- VIEW UNTUK ANALISIS & MANAGER
-- =====================================================================

-- View A: Kasus aktif level item lengkap umur
CREATE OR REPLACE VIEW `v_kasus_aktif` AS
SELECT
    k.*,
    DATEDIFF(CURDATE(), COALESCE(k.tgl_dokumen, DATE(k.created_at))) AS umur_hari
FROM `kasus` k
WHERE k.status <> 'selesai';

-- View B: Rekap kasus terbuka per dokumen / nota
CREATE OR REPLACE VIEW `v_kasus_dokumen` AS
SELECT
    k.jenis,
    k.kode_cabang,
    k.kode_toko,
    MAX(k.nama_toko) AS nama_toko,
    k.docno,
    COUNT(*) AS jumlah_item,
    SUM(k.qty) AS total_qty,
    SUM(k.nilai) AS total_nilai,
    MIN(COALESCE(k.tgl_dokumen, DATE(k.created_at))) AS tgl_dokumen,
    DATEDIFF(CURDATE(), MIN(COALESCE(k.tgl_dokumen, DATE(k.created_at)))) AS umur_hari,
    MAX(FIELD(k.prioritas, 'rendah', 'sedang', 'tinggi', 'urgent')) AS level_prioritas,
    MAX(k.status = 'eskalasi') AS ada_eskalasi,
    MIN(k.id) AS kasus_id_perwakilan
FROM `kasus` k
WHERE k.status <> 'selesai'
GROUP BY k.jenis, k.kode_cabang, k.kode_toko, k.docno;

-- View C: Rekap per cabang untuk Manager & Collector (Antrian Cabang)
CREATE OR REPLACE VIEW `v_antrian_manager` AS
SELECT
    c.kode_cabang,
    c.nama_cabang,
    COUNT(DISTINCT d.docno) AS total_nota,
    SUM(d.total_nilai) AS total_nilai,
    MAX(d.umur_hari) AS umur_tertua_hari,
    GROUP_CONCAT(DISTINCT d.jenis) AS daftar_jenis,
    ROUND(SUM(ABS(d.total_nilai)) * (1 + MAX(d.umur_hari) / 30), 2) AS skor_prioritas
FROM `master_cabang` c
JOIN `v_kasus_dokumen` d ON d.kode_cabang = c.kode_cabang
WHERE c.is_aktif = 1
GROUP BY c.kode_cabang, c.nama_cabang;