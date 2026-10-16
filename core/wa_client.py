import time
from typing import Optional, Any
import requests
from core import config
from core.jobio import logger

def send_whatsapp_message(
    target_jid: str,
    text: str,
    mentions: Optional[list[str]] = None,
    max_retries: int = 2,
    retry_delay: int = 5,
) -> tuple[bool, Optional[str], Optional[dict[str, Any]]]:
    """
    Mengirim pesan teks ke WhatsApp via Evolution API.
    Mendukung direct number dan group JID (@g.us) serta mention list.
    Return (success, evolution_message_id, response_json).
    """
    endpoint = f"{config.EVO_URL}/message/sendText/{config.EVO_INSTANCE}"
    headers = {
        "apikey": config.EVO_APIKEY,
        "Content-Type": "application/json",
    }

    payload: dict[str, Any] = {
        "number": target_jid,
        "text": text,
        "delay": 1200,
        "linkPreview": True,
    }
    if mentions:
        payload["mentioned"] = mentions

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=45)
            if resp.status_code in (200, 201):
                data = resp.json()
                msg_id = data.get("key", {}).get("id") or data.get("messageId")
                logger.info(f"✓ Berhasil kirim pesan ke {target_jid} (ID: {msg_id})")
                return True, msg_id, data

            logger.warning(
                f"Gagal kirim ke {target_jid} [HTTP {resp.status_code}]: {resp.text[:200]}"
            )
            # 4xx client error tidak perlu di-retry (nomor invalid, dll)
            if 400 <= resp.status_code < 500:
                return False, None, {"error": resp.text, "status_code": resp.status_code}

        except Exception as e:
            logger.warning(f"Exception saat kirim ke {target_jid} (attempt {attempt}): {e}")

        if attempt < max_retries:
            time.sleep(retry_delay)

    return False, None, {"error": "Max retries exceeded"}

def send_whatsapp_media(
    target_jid: str,
    base64_data: str,
    filename: str,
    caption: str,
    mimetype: str = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    max_retries: int = 2,
    retry_delay: int = 5,
) -> tuple[bool, Optional[str], Optional[dict[str, Any]]]:
    """
    Mengirim file dokumen (Excel/PDF) via Evolution API sendMedia.
    """
    endpoint = f"{config.EVO_URL}/message/sendMedia/{config.EVO_INSTANCE}"
    headers = {
        "apikey": config.EVO_APIKEY,
        "Content-Type": "application/json",
    }
    payload = {
        "number": target_jid,
        "mediatype": "document",
        "mimetype": mimetype,
        "media": base64_data,
        "fileName": filename,
        "caption": caption,
    }

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=60)
            if resp.status_code in (200, 201):
                data = resp.json()
                msg_id = data.get("key", {}).get("id") or data.get("messageId")
                logger.info(f"✓ Berhasil kirim media {filename} ke {target_jid}")
                return True, msg_id, data

            logger.warning(
                f"Gagal kirim media ke {target_jid} [HTTP {resp.status_code}]: {resp.text[:200]}"
            )
            if 400 <= resp.status_code < 500:
                return False, None, {"error": resp.text, "status_code": resp.status_code}
        except Exception as e:
            logger.warning(f"Exception kirim media ke {target_jid}: {e}")

        if attempt < max_retries:
            time.sleep(retry_delay)

    return False, None, {"error": "Max retries exceeded"}
