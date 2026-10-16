import sys
import json
import logging
from typing import Callable, Any

# Setup basic stderr logger
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    stream=sys.stderr,
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("agent")

def run_job(main_func: Callable[[], dict[str, Any]]) -> None:
    """
    Decorator / runner pattern standar untuk semua jobs.
    - Semua log progres mengalir ke stderr.
    - Baris terakhir di stdout dijamin 1 baris JSON valid untuk n8n parser.
    - Exit code 0 jika sukses, 1 jika error fatal.
    """
    try:
        result = main_func()
        if not isinstance(result, dict):
            result = {"status": "success", "result": result}
        # Cetak baris terakhir ke stdout
        print(json.dumps(result))
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Job gagal dieksekusi: {e}")
        err_payload = {
            "status": "error",
            "error_type": type(e).__name__,
            "error_message": str(e),
        }
        print(json.dumps(err_payload))
        sys.exit(1)
