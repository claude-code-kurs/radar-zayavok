"""Уведомления в Telegram-бот.

Токен бота и id чата, куда слать, берутся из `.env` — в код они не вписываются.
Новой библиотеки не нужно: у Telegram обычный HTTP API, а `requests` в проекте уже
стоит с урока 7.

Проверить, что подключение работает:

    python notify.py "тестовое сообщение"
"""

import logging
import os

import requests
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

TIMEOUT_SECONDS = 15


def send(text):
    """Отправляет сообщение в бот. Возвращает True, если получилось.

    Никогда не поднимает исключение наружу: уведомление — дело второстепенное, и
    из-за упавшего бота не должна падать ни разметка заявок, ни отправка формы на
    сайте. Причина неудачи уходит в лог, работа продолжается.
    """
    if not BOT_TOKEN or not CHAT_ID:
        logging.warning(
            "Уведомление не отправлено: в .env нет TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID"
        )
        return False

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True},
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as error:
        logging.warning("Уведомление не отправлено, сбой связи: %s", error)
        return False

    if response.status_code != 200:
        # Тело ответа печатаем всегда: один код без причины ничего не объясняет.
        logging.warning(
            "Уведомление не отправлено, ответ Telegram %s: %s",
            response.status_code,
            response.text[:300],
        )
        return False

    return True


if __name__ == "__main__":
    import sys

    import logs

    logs.setup()
    message = sys.argv[1] if len(sys.argv) > 1 else "Радар на связи."
    print("Отправлено." if send(message) else "Не отправлено, причина в логе выше.")
