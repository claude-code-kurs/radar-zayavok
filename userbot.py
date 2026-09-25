"""Юзербот: читает публичную группу опросом истории.

Этот скрипт запускает человек, своими руками, в своём терминале. При первом
запуске Telethon спросит код подтверждения из Telegram, а если на аккаунте
включён облачный пароль — то и его. Агент этот скрипт не запускает никогда:
код и пароль не должны попасть в переписку с агентом.

    python userbot.py
"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import RPCError
from telethon.tl.types import Channel, Chat, User

# Группа-источник. Для публичной — username из адреса t.me/<username>, строкой,
# без «t.me/» и без «@». Для закрытой, в которой аккаунт состоит, — её id числом,
# со знаком минус и без кавычек (например -1001234567890).
# Значение ниже — заглушка, впишите вместо неё свою группу.
SOURCE = "pixeltechspec"

# Как часто спрашивать у Telegram новые сообщения, в секундах.
# Меньше 20 секунд не ставим, пока лимиты Telegram не проверены.
POLL_INTERVAL = 30

# Сколько последних сообщений показать при первом опросе, чтобы результат был виден сразу.
FIRST_POLL_LIMIT = 5

# Сколько сообщений забирать за один обычный опрос.
POLL_LIMIT = 100

load_dotenv()

API_ID = os.getenv("API_ID", "")
API_HASH = os.getenv("API_HASH", "")

# Файл сессии кладём рядом со скриптом, а не туда, откуда запущен терминал.
SESSION_PATH = Path(__file__).parent / "userbot"


def chat_kind(entity):
    """Что именно мы открыли — чтобы не перепутать группу с диалогом с самим собой."""
    if isinstance(entity, User):
        return "пользователь (это не группа)"
    if isinstance(entity, Channel):
        return "канал" if entity.broadcast else "супергруппа"
    if isinstance(entity, Chat):
        return "группа"
    return "неизвестный тип"


def chat_name(entity):
    title = getattr(entity, "title", None)
    if title:
        return title
    username = getattr(entity, "username", None)
    if username:
        return f"@{username}"
    return str(getattr(entity, "id", "без названия"))


async def author_of(message):
    """Кто написал: в группе — живой человек, в канале автор — сам канал."""
    sender = await message.get_sender()
    if sender is None:
        return chat_name(message.chat) if message.chat else "неизвестно"
    username = getattr(sender, "username", None)
    if username:
        return f"@{username}"
    name = " ".join(
        part for part in (getattr(sender, "first_name", ""), getattr(sender, "last_name", "")) if part
    ).strip()
    return name or getattr(sender, "title", "") or "неизвестно"


async def print_messages(messages):
    """Печатает сообщения от старых к новым и возвращает самый большой id."""
    largest_id = 0
    for message in reversed(messages):
        text = (message.text or "").strip() or "[служебное сообщение без текста]"
        author = await author_of(message)
        print(f"[{message.date:%Y-%m-%d %H:%M}] {author}: {text}")
        largest_id = max(largest_id, message.id)
    return largest_id


async def resolve_source(client):
    try:
        return await client.get_entity(SOURCE)
    except (ValueError, RPCError) as error:
        raise SystemExit(
            f"Чат «{SOURCE}» не найден. Причин две, и по ответу Telegram их не различить:\n"
            f"  1) опечатка в username или id;\n"
            f"  2) чат закрытый, а аккаунт юзербота в нём не состоит.\n"
            f"Ответ библиотеки: {error}"
        )


async def main():
    if not API_ID or not API_HASH:
        raise SystemExit("В .env нет API_ID или API_HASH — впишите значения с my.telegram.org.")

    client = TelegramClient(str(SESSION_PATH), int(API_ID), API_HASH)
    await client.start()

    source = await resolve_source(client)
    print(f"Открыт {chat_kind(source)}: {chat_name(source)}")

    last_id = 0
    while True:
        if last_id:
            messages = await client.get_messages(source, limit=POLL_LIMIT, min_id=last_id)
        else:
            messages = await client.get_messages(source, limit=FIRST_POLL_LIMIT)

        largest_id = await print_messages(messages)
        if largest_id:
            last_id = largest_id
        print(f"За опрос получено сообщений: {len(messages)}")

        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Ctrl+C — это обычное завершение, а не авария: выходим одной строкой,
        # без десятка строк трассировки.
        print("Остановлено.")
