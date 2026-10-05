def check_referral(answers: dict, protocol: dict) -> dict:
    """answers: {criterion: bool}. Возвращает вердикт по большинству 'да'."""
    yes = [k for k, v in answers.items() if v]
    need = len(yes) > 0
    return {"referral_needed": need, "positive_criteria": yes,
            "verdict": "Показано направление/госпитализация — сверьте с КР." if need else "Критериев не выявлено. Решение принимает врач.",
            "protocol": protocol.get("title","")}
