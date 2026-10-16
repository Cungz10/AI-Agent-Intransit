import json
from typing import Optional, Any
from openai import OpenAI
from core import config
from core.jobio import logger
from core import db

def get_client() -> OpenAI:
    """Menginisialisasi OpenAI client yang terhubung ke 9router."""
    return OpenAI(
        base_url=config.LLM_BASE_URL,
        api_key=config.LLM_API_KEY,
    )

def check_token_budget() -> tuple[bool, int]:
    """Mengecek pemakaian token harian terhadap budget."""
    conn = db.get_connection(config.DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COALESCE(SUM(token_input + token_output), 0)
        FROM agent_run
        WHERE mulai_at >= CURDATE()
        """
    )
    total_token = int(cur.fetchone()[0])
    cur.close()
    conn.close()

    within_budget = total_token < config.LLM_DAILY_TOKEN_BUDGET
    return within_budget, total_token

def call_llm_json(
    messages: list[dict[str, str]],
    model: Optional[str] = None,
    temperature: float = 0.2,
) -> tuple[dict[str, Any], int, int]:
    """
    Memanggil LLM dengan enforcement JSON output.
    Return (parsed_dict, token_input, token_output).
    """
    within_budget, current_tokens = check_token_budget()
    if not within_budget:
        raise RuntimeError(
            f"Token budget harian terlampaui! Pemakaian hari ini: {current_tokens} "
            f"(Batas: {config.LLM_DAILY_TOKEN_BUDGET})"
        )

    model_to_use = model or config.LLM_MODEL_CHEAP
    client = get_client()

    logger.info(f"Memanggil LLM model {model_to_use} via 9router...")
    response = client.chat.completions.create(
        model=model_to_use,
        messages=messages,
        temperature=temperature,
        response_format={"type": "json_object"},
    )

    usage = response.usage
    token_in = usage.prompt_tokens if usage else 0
    token_out = usage.completion_tokens if usage else 0

    content = (response.choices[0].message.content or "{}").strip()
    if content.startswith("```"):
        import re
        content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.IGNORECASE)
        content = re.sub(r"\s*```$", "", content)

    try:
        parsed = json.loads(content)
    except Exception as e:
        logger.error(f"Gagal parse JSON LLM: {content}")
        raise ValueError(f"LLM tidak mengembalikan valid JSON: {e}")

    return parsed, token_in, token_out
