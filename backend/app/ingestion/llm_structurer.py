"""LLM-структурирование неструктурированных разделов. Строго extractive."""
EXTRACT_PROMPT = """Извлеки только то, что ЯВНО присутствует в тексте. Ничего не добавляй от себя.
При отсутствии данных верни null. Верни JSON с ключами: definition, etiology_epidemiology,
classification, complications, prevention, prognosis, follow_up."""
def structure_with_llm(text: str, client) -> dict:
    try:
        import json
        raw = client.complete("Ты — точный медицинский экстрактор. " + EXTRACT_PROMPT, text[:8000])
        # mock возвращает не-JSON -> fallback
        if "{" in raw and "}" in raw:
            return json.loads(raw[raw.find("{"):raw.rfind("}")+1])
    except Exception:
        pass
    return {"definition": text[:1500] if text else None, "etiology_epidemiology": None,
            "classification": None, "complications": [], "prevention": [],
            "prognosis": [], "follow_up": []}
