"""Юзербот: обходит источники, отсеивает мусор и пишет находки в базу.

Этот скрипт запускает человек, своими руками, в своём терминале. При первом
запуске Telethon спросит номер телефона, код подтверждения из Telegram, а если на
аккаунте включён облачный пароль — то и его. Агент этот скрипт не запускает никогда:
код и пароль не должны попасть в переписку с агентом.

    python userbot.py
"""

import asyncio
import json
import os
from datetime import timezone
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import RPCError
from telethon.tl.types import Channel, Chat, User

from db import (
    add_finding_to_source,
    content_hash_exists,
    get_keywords,
    get_sources,
    insert_request,
    mark_source_seen,
    recent_texts,
    request_exists,
    set_source_chat_id,
)
from filters import content_hash, is_near_duplicate, matched_keywords, prepare_text
from settings import FIRST_RUN_MESSAGES, MAX_MESSAGES_PER_SOURCE

# Как часто обходить все источники по кругу, в секундах.
# Меньше 20 секунд не ставим, пока лимиты Telegram не проверены.
POLL_INTERVAL = 30

# Сколько последних заявок сравнивать при проверке на почти одинаковые тексты.
RECENT_TEXTS_TO_COMPARE = 200

# С какого числа прочитанных сообщений имеет смысл говорить, что словарь не отбросил
# ничего: на двух-трёх сообщениях это ещё не сигнал, а совпадение.
SUSPICIOUS_FROM = 5

load_dotenv()

API_ID = os.getenv("API_ID", "")
API_HASH = os.getenv("API_HASH", "")

# Файл сессии и файл состояния кладём рядом со скриптом, а не туда,
# откуда запущен терминал.
SESSION_PATH = Path(__file__).parent / "userbot"
STATE_PATH = Path(__file__).parent / "state.json"


def load_state():
    """id последнего обработанного сообщения по каждому чату.

    Ключ — числовой id чата, а не username: username у группы можно сменить,
    id живёт с ней всегда.
    """
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def to_iso(moment):
    """Дата строкой ISO 8601 в UTC — в таком виде её хранит база."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def message_link(entity, message):
    """Ссылка на сообщение: у публичной группы собирается из её username."""
    username = getattr(entity, "username", None)
    if username:
        return f"https://t.me/{username}/{message.id}"
    return ""


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


async def resolve_source(client, address):
    """Находит чат по username или id. При неудаче честно называет обе причины."""
    try:
        return await client.get_entity(address)
    except (ValueError, RPCError) as error:
        print(
            f"Источник «{address}» не найден. Причин две, и по ответу Telegram их не различить:\n"
            f"  1) опечатка в username или id;\n"
            f"  2) чат закрытый, а аккаунт юзербота в нём не состоит.\n"
            f"  Ответ библиотеки: {error}"
        )
        return None


async def fetch_messages(client, entity, last_id):
    """Сообщения от старых к новым, начиная с сохранённого состояния.

    Порядок именно такой, и это не мелочь. Если читать от новых к старым и упереться
    в потолок, то сообщения между сохранённым состоянием и забранной сотней при
    следующем заходе окажутся «старыми» и не заберутся уже никогда.
    """
    if last_id:
        return await client.get_messages(
            entity, limit=MAX_MESSAGES_PER_SOURCE, min_id=last_id, reverse=True
        )

    # Первый заход в источник: состояния по нему нет, и читать канал с самого начала
    # истории незачем — берём последние сообщения и разворачиваем в хронологический порядок.
    messages = await client.get_messages(entity, limit=FIRST_RUN_MESSAGES)
    return list(reversed(messages))


async def process_source(client, source, state, keywords):
    """Один источник за один заход: прочитать, отсеять, записать находки.

    Список ключевых слов приходит снаружи: его перечитывают из базы на каждом обходе,
    чтобы правка на странице настроек в кабинете долетала до уже запущенного юзербота.
    """
    entity = await resolve_source(client, source["name"])
    if entity is None:
        return

    chat_id = entity.id
    if str(source["chat_id"] or "") != str(chat_id):
        set_source_chat_id(source["id"], chat_id)

    last_id = state.get(str(chat_id), 0)
    messages = await fetch_messages(client, entity, last_id)

    written = 0
    skipped_seen = 0
    skipped_duplicate = 0
    caught_by_schema = 0
    with_text = 0
    passed_keywords = 0
    newest_message_at = None

    for message in messages:
        # Состояние двигаем на каждом сообщении, а не одним махом в конце: если упрёмся
        # в потолок или скрипт остановят, следующий заход продолжит ровно отсюда.
        state[str(chat_id)] = message.id

        if message.date and (newest_message_at is None or message.date > newest_message_at):
            newest_message_at = message.date

        # Порядок важен: сначала разметка и служебная приписка канала уходят из текста,
        # и только потом текст идёт на словарный отсев и на проверки повторов.
        text = prepare_text(message.text)
        if not text:
            # Служебные сообщения — о создании группы, о новых участниках — без текста.
            # Сюда же попадает сообщение, от которого после обрезки приписки ничего не осталось.
            continue

        with_text += 1
        matched = matched_keywords(text, keywords)
        if not matched:
            continue
        passed_keywords += 1

        source_message_id = f"{chat_id}/{message.id}"
        if request_exists(source_message_id):
            skipped_seen += 1
            continue

        text_hash = content_hash(text)
        if content_hash_exists(text_hash):
            skipped_duplicate += 1
            continue
        if is_near_duplicate(text, recent_texts(RECENT_TEXTS_TO_COMPARE)):
            skipped_duplicate += 1
            continue

        written_now = insert_request(
            text=text,
            author=await author_of(message),
            source=chat_name(entity),
            source_message_id=source_message_id,
            message_url=message_link(entity, message),
            created_at=to_iso(message.date),
            matched_keywords=", ".join(matched),
            edit_date=to_iso(message.edit_date) if message.edit_date else "",
            content_hash=text_hash,
        )
        if not written_now:
            # Повтор проскочил проверку и упёрся в UNIQUE. Считаем отдельно: это не
            # обычный дубль, а признак, что проверка перед записью чего-то не видит.
            caught_by_schema += 1
            continue

        add_finding_to_source(source["id"])
        written += 1

    # Дату последнего сообщения запоминаем, даже если ни одно не прошло фильтры:
    # старая дата здесь означает, что источник замолчал, а не что радар сломался.
    if newest_message_at:
        mark_source_seen(source["id"], to_iso(newest_message_at))

    print(
        f"{chat_name(entity)} ({chat_kind(entity)}): "
        f"новых сообщений {len(messages)}, записано {written}"
    )
    if skipped_duplicate:
        print(f"  отброшено как повтор: {skipped_duplicate}")
    if skipped_seen:
        # Эти строки появляются только тогда, когда есть что сказать: счётчик,
        # который всегда показывает ноль, человек читает как ошибку.
        print(f"  уже было в базе: {skipped_seen}")
    if caught_by_schema:
        print(
            f"  ВНИМАНИЕ: повтор остановила схема базы, а не проверка: {caught_by_schema}. "
            "Проверка на дубли чего-то не видит — стоит разобраться, пока это не стало нормой"
        )
    if with_text >= SUSPICIOUS_FROM and passed_keywords == with_text:
        print(
            f"  ВНИМАНИЕ: словарь не отбросил ни одного сообщения из {with_text} — "
            "скорее сломан, чем удачлив. Проверьте, не совпадает ли ключевое слово "
            "со служебной припиской канала"
        )
    if len(messages) >= MAX_MESSAGES_PER_SOURCE:
        print("  упёрлись в потолок за этот заход — осталось ещё, следующий заход продолжит")


async def main():
    if not API_ID or not API_HASH:
        raise SystemExit("В .env нет API_ID или API_HASH — впишите значения с my.telegram.org.")

    client = TelegramClient(str(SESSION_PATH), int(API_ID), API_HASH)
    await client.start()

    while True:
        # Источники и ключевые слова перечитываем на каждом обходе, а не один раз при
        # старте: их правят на странице настроек в кабинете, и правка должна долетать
        # до уже запущенного юзербота, без перезапуска.
        sources = get_sources()
        keywords = [row["word"] for row in get_keywords()]
        if not sources:
            raise SystemExit(
                "В таблице sources нет ни одного источника. Добавьте их на странице "
                "настроек в кабинете и запустите снова."
            )
        if not keywords:
            raise SystemExit(
                "В таблице keywords нет ни одного слова — отсев пропустил бы всё подряд. "
                "Добавьте слова на странице настроек в кабинете."
            )

        state = load_state()
        for source in sources:
            await process_source(client, source, state, keywords)
            save_state(state)

        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Ctrl+C — это обычное завершение, а не авария: выходим одной строкой,
        # без десятка строк трассировки.
        print("Остановлено.")
