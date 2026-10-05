# DECISIONS
1. Threshold 0.75→0.12: TF-IDF fallback даёт низкие абсолютные скоры (релевант 0.23, нерелевант 0.08). Порог 0.12 разделяет классы. При переходе на embeddings вернуть 0.75 (настройка .env LLM_THRESHOLD).
2. Chroma optional + TF-IDF fallback: индексация работает без torch/CUDA из коробки.
3. MockLLM по умолчанию: end-to-end тест без ключа; замена — только .env.
4. SQLite по умолчанию: запуск без Docker врачу; Postgres — в compose.
5. Таблицы доз — только rule-based, не в LLM (защита цифр).
