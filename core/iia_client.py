import time
from html.parser import HTMLParser
import requests
from core import config
from core.jobio import logger

class TokenParser(HTMLParser):
    """Parse CSRF token dari halaman login IIAWeb."""
    def __init__(self):
        super().__init__()
        self.token = None

    def handle_starttag(self, tag, attrs):
        if tag == "input":
            d = dict(attrs)
            if d.get("name") == "__RequestVerificationToken":
                self.token = d.get("value")

def get_csrf_token(session: requests.Session, login_url: str) -> str:
    resp = session.get(login_url, timeout=30)
    resp.raise_for_status()
    parser = TokenParser()
    parser.feed(resp.text)
    if not parser.token:
        raise ValueError("CSRF token tidak ditemukan di halaman login!")
    return parser.token

def create_authenticated_session(max_retries: int = 3, retry_delay: int = 20) -> requests.Session:
    """
    Melakukan login ke IIAWeb dengan sistem retry & backoff linear.
    Mengembalikan session terautentikasi lengkap dengan header standar.
    """
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            session = requests.Session()
            session.headers.update({
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
            })

            logger.info(f"Mengambil CSRF token dari {config.IIA_LOGIN_URL}...")
            token = get_csrf_token(session, config.IIA_LOGIN_URL)

            logger.info(f"Login ke IIAWeb sebagai {config.IIA_USERNAME} (percobaan {attempt}/{max_retries})...")
            payload = {
                "__RequestVerificationToken": token,
                config.IIA_FIELD_USER: config.IIA_USERNAME,
                config.IIA_FIELD_PASS: config.IIA_PASSWORD,
                "RememberMe": "false",
            }
            resp = session.post(config.IIA_LOGIN_URL, data=payload, timeout=30, allow_redirects=True)

            if "login" in resp.url.lower():
                raise ValueError("Login gagal! Cek IIA_USERNAME atau IIA_PASSWORD di .env")

            logger.info("✓ Login IIAWeb berhasil!")
            return session

        except Exception as e:
            last_err = e
            logger.warning(f"Percobaan login {attempt}/{max_retries} gagal: {e}")
            if attempt < max_retries:
                delay = retry_delay * attempt
                logger.info(f"Menunggu {delay} detik sebelum retry...")
                time.sleep(delay)

    raise RuntimeError(f"Gagal login ke IIAWeb setelah {max_retries} percobaan: {last_err}")

if __name__ == "__main__":
    logger.info("Testing IIAWeb Login Session...")
    try:
        s = create_authenticated_session(max_retries=1)
        logger.info("✓ Tes session IIAWeb selesai tanpa error.")
    except Exception as e:
        logger.error(f"✗ Gagal: {e}")
