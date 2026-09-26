"""Один запрос к модели через шлюз, совместимый с форматом OpenAI.

Адрес, ключ и имя модели берутся из `.env` и в код не попадают. Библиотека — `requests`,
обычный HTTP-клиент: так курс не привязан к SDK конкретного шлюза, а у российских
шлюзов адреса и имена моделей разные.
"""

import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("LLM_API_URL", "")
API_KEY = os.getenv("LLM_API_KEY", "")
MODEL = os.getenv("LLM_MODEL", "")

TIMEOUT_SECONDS = 60


class ModelUnavailable(Exception):
    """Ответ не получен: сеть, таймаут, ошибка шлюза.

    Виноват канал связи, а не данные. Запись в этом случае не трогаем вообще —
    следующий прогон подберёт её сам.
    """


class ModelAnswerError(Exception):
    """Ответ получен, но разобрать его не удалось.

    Виновата модель: ответила не тем форматом. Запись помечаем «не проверено ИИ»,
    чтобы она не уходила в модель каждый прогон заново, и идём дальше.
    """


def check_settings():
    """Проверяет, что доступ к модели настроен, — до первого запроса."""
    missing = [
        name
        for name, value in (("LLM_API_URL", API_URL), ("LLM_API_KEY", API_KEY), ("LLM_MODEL", MODEL))
        if not value
    ]
    if missing:
        raise SystemExit(f"В .env не заполнено: {', '.join(missing)}")


def strip_code_block(answer):
    """Снимает обрамление блоком кода, если модель его добавила.

    Известное поведение части моделей — обернуть JSON в ```json ... ```. Это не ошибка
    нашего кода, поэтому чиним до разбора, а не считаем запись непроверенной.
    """
    text = answer.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    return text.strip()


def ask_model(system_prompt, message_text):
    """Задаёт модели один вопрос и возвращает разобранный JSON-ответ словарём."""
    try:
        response = requests.post(
            f"{API_URL.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message_text},
                ],
                "temperature": 0,
            },
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as error:
        raise ModelUnavailable(str(error)) from error

    if response.status_code != 200:
        # Тело ответа печатаем всегда: один код ошибки без причины бесполезен.
        raise ModelUnavailable(f"код {response.status_code}, ответ: {response.text[:300]}")

    try:
        answer = response.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError) as error:
        raise ModelAnswerError(f"неожиданная структура ответа шлюза: {error}") from error

    try:
        return json.loads(strip_code_block(answer))
    except ValueError as error:
        raise ModelAnswerError(f"ответ не разбирается как JSON: {answer[:200]}") from error
