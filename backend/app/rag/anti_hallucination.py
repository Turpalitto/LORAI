import re
REFUSAL = "В загруженных клинических рекомендациях информация по этому вопросу не найдена."
def check_numbers(answer: str, chunks: list[dict]) -> str:
    nums = set(re.findall(r"\d+(?:[.,]\d+)?\s*(?:мг|мл|г|мкг|МЕ|%)?", answer))
    ctx = " ".join(c.get("text","") for c in chunks)
    bad = [n for n in nums if n.strip() and n.strip().split()[0] not in ctx]
    if bad:
        return answer + "\n\n⚠️ Числа требуют проверки врачом: " + ", ".join(bad[:5])
    return answer
def should_refuse(chunks: list[dict], threshold: float) -> bool:
    if not chunks: return True
    return max((c.get("score", 0) for c in chunks), default=0) < threshold
