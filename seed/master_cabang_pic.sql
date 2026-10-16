USE `intransit_agent`;

-- 24 Master Cabang dari script download_rekap_intransit.py
INSERT INTO `master_cabang` (`kode_cabang`, `nama_cabang`, `is_aktif`) VALUES
('G001', 'Jakarta 1 (G001)', 1),
('G026', 'Tangerang 1 (G026)', 1),
('G033', 'Tangerang 2 (G033)', 1),
('G107', 'Parung (G107)', 1),
('G113', 'Bogor 1 (G113)', 1),
('G117', 'Bogor 2 (G117)', 1),
('G137', 'Jakarta 2 (G137)', 1),
('G143', 'Jambi (G143)', 1),
('G146', 'Lombok (G146)', 1),
('G157', 'Lebak (G157)', 1),
('G165', 'Bengkulu (G165)', 1),
('G174', 'Ternate (G174)', 1),
('G219', 'Bintan (G219)', 1),
('G224', 'Bima (G224)', 1),
('G236', 'Sorong (G236)', 1),
('G237', 'Kupang (G237)', 1),
('G260', 'Bangka Belitung (G260)', 1),
('G263', 'Jayapura (G263)', 1),
('G265', 'Flores (G265)', 1),
('G272', 'Sumba (G272)', 1),
('G273', 'Manokwari (G273)', 1),
('G283', 'Merauke (G283)', 1),
('G295', 'Sukabumi (G295)', 1),
('G298', 'Alor (G298)', 1)
ON DUPLICATE KEY UPDATE `nama_cabang` = VALUES(`nama_cabang`), `is_aktif` = VALUES(`is_aktif`);
