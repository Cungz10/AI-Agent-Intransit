import base64, json, requests, sys, time
from datetime import datetime, timedelta

# ====== CONFIG ======
API_KEY = "ISI_API_KEY_KAMU_DI_SINI"   # tempel key Evolution lo di sini
API_URL = "http://localhost:8080/message/sendMedia/rekap_intransit"

targets = [
    "120363404708425192@g.us",
    "628883800266-1502079935@g.us",   # hapus baris ini kalau Cungz belum masuk grup ini
]

DELAY_BETWEEN_SEND = 3  # detik, jeda antar tujuan
MAX_RETRY = 2           # percobaan ulang (cuma untuk error sementara)
RETRY_DELAY = 5         # detik sebelum retry

# ====== FILE ======
now = datetime.now() - timedelta(days=1)
months = ['January','February','March','April','May','June','July','August','September','October','November','December']
filename = f"Rekap_Intransit_{now.day}-{months[now.month-1]}-{now.year}.xlsx"
filepath = rf"D:\intbk\rekap_intransit\{filename}"

try:
    with open(filepath, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
except FileNotFoundError:
    print(json.dumps({"error": f"File tidak ditemukan: {filepath}"}))
    sys.exit(1)

mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
caption = (
    f"Selamat Pagi Bapak/Ibu 🙏\n\n"
    f"Bersama pesan ini kami lampirkan *{filename}* sebagai laporan rekap intransit harian.\n\n"
    f"Mohon kiranya dapat segera ditindaklanjuti dan diproses pada hari ini. "
    f"Apabila terdapat kendala atau ketidaksesuaian data, harap segera konfirmasi.\n\n"
    f"Terima kasih atas perhatian dan kerjasamanya. 🙏"
)

# ====== KIRIM ======
def send_to(number):
    for attempt in range(1, MAX_RETRY + 1):
        try:
            res = requests.post(
                API_URL,
                headers={"apikey": API_KEY},
                json={
                    "number": number,
                    "mediatype": "document",
                    "mimetype": mimetype,
                    "media": b64,
                    "fileName": filename,
                    "caption": caption,
                },
                timeout=60,
            )
            print(f"[{number}] attempt {attempt} -> {res.status_code} {res.text[:300]}")

            if res.status_code == 201:
                return True

            # 4xx = masalah permanen (bukan member grup, JID salah, dll). Retry percuma.
            if 400 <= res.status_code < 500:
                print(f"[{number}] error {res.status_code}, nggak di-retry.")
                return False

        except requests.exceptions.RequestException as e:
            print(f"[{number}] attempt {attempt} -> EXCEPTION: {e}")

        if attempt < MAX_RETRY:
            print(f"[{number}] retrying in {RETRY_DELAY}s...")
            time.sleep(RETRY_DELAY)

    return False

sukses, gagal = [], []

for i, number in enumerate(targets):
    (sukses if send_to(number) else gagal).append(number)
    if i < len(targets) - 1:
        time.sleep(DELAY_BETWEEN_SEND)

if gagal:
    print(f"GAGAL kirim ke: {', '.join(gagal)}")

# Baris terakhir = JSON, gampang di-parse node Code di n8n
print(json.dumps({"filename": filename, "sukses": sukses, "gagal": gagal}))

# Merah di n8n cuma kalau SEMUA tujuan gagal
sys.exit(0 if sukses else 1)
