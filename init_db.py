"""Создаёт таблицы базы и наполняет их начальными данными.

Запускать один раз:

    python init_db.py
"""

from db import connect

SCHEMA_REQUESTS = """
CREATE TABLE IF NOT EXISTS requests (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    text              TEXT NOT NULL,
    author            TEXT,
    source            TEXT,
    -- UNIQUE здесь — не дубль проверки в коде, а последняя линия: проверка перед записью
    -- считает повторы и не сыпет ошибками, а схема физически не даёт записать пару
    -- «чат и сообщение» второй раз, даже если проверка чего-то не увидела.
    -- У заявок с сайта (урок 8) в этом поле NULL: пустых строк UNIQUE допустит только одну,
    -- а NULL — сколько угодно.
    source_message_id TEXT UNIQUE,
    message_url       TEXT,
    created_at        TEXT,
    matched_keywords  TEXT,
    edit_date         TEXT,
    content_hash      TEXT,
    ai_label          TEXT,
    ai_reason         TEXT,
    status            TEXT DEFAULT 'новое'
)
"""

# Источник — отдельная сущность, а не свойство находки: у источника, который пока не дал
# ни одной заявки, нет строки в requests, чтобы записать на неё «когда там видели
# последнее сообщение». Поэтому своя таблица.
SCHEMA_SOURCES = """
CREATE TABLE IF NOT EXISTS sources (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    chat_id        TEXT,
    last_seen_at   TEXT,
    findings_count INTEGER DEFAULT 0
)
"""

# Источники-заглушки: name — это то, чем адресуем чат (username публичной группы или
# числовой id закрытой, в которой аккаунт состоит). Впишите вместо них свои группы.
# chat_id заполнится сам при первом подключении — числовой id чата узнаётся только там.
TEST_SOURCES = [
    ("imya_pervoy_gruppy", None),
    ("imya_vtoroy_gruppy", None),
]

# Выдуманные заявки — чтобы в кабинете было что смотреть до появления настоящих.
TEST_REQUESTS = [
    (
        "Ищу того, кто соберёт бота для записи в барбершоп: слоты, напоминания, отмена. Бюджет обсуждаем.",
        "@marina_pro",
        "Фриланс: боты и автоматизация",
        "botfreelance/1841",
        "https://t.me/botfreelance/1841",
        "2026-09-21T08:14:00Z",
    ),
    (
        "Нужен парсер объявлений с сайта поставщика в гугл-таблицу, раз в сутки. Кто делал похожее?",
        "Дмитрий К.",
        "Автоматизация для бизнеса",
        "bizavtomat/903",
        "https://t.me/bizavtomat/903",
        "2026-09-21T11:42:00Z",
    ),
    (
        "Требуется доработать существующего бота на Python: добавить оплату и выгрузку заявок в CRM.",
        "@it_zakaz",
        "Работа для программистов",
        "devwork/25517",
        "https://t.me/devwork/25517",
        "2026-09-22T06:05:00Z",
    ),
    (
        "Кто возьмётся настроить рассылку по клиентам из базы, с проверкой ответов? Срок — неделя.",
        "Ольга",
        "Фриланс: боты и автоматизация",
        "botfreelance/1877",
        "https://t.me/botfreelance/1877",
        "2026-09-22T15:30:00Z",
    ),
    (
        "Ищем подрядчика на бота-помощника для отдела продаж: собирать заявки из чатов и присылать сводку утром.",
        "@sales_lead",
        "Автоматизация для бизнеса",
        "bizavtomat/941",
        "https://t.me/bizavtomat/941",
        "2026-09-23T07:20:00Z",
    ),
]


def main():
    conn = connect()
    try:
        conn.execute(SCHEMA_REQUESTS)
        conn.execute(SCHEMA_SOURCES)

        # И заявки, и источники добавляем только в пустые таблицы: скрипт можно
        # запускать повторно, и от второго запуска в базе не должно появиться
        # ни лишних тестовых заявок, ни заглушек рядом с настоящими источниками.
        if not conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0]:
            conn.executemany(
                """
                INSERT INTO requests (
                    text, author, source, source_message_id, message_url, created_at,
                    ai_label, ai_reason, status
                )
                VALUES (?, ?, ?, ?, ?, ?, '', '', 'новое')
                """,
                TEST_REQUESTS,
            )
            print(f"Добавлено тестовых заявок: {len(TEST_REQUESTS)}")

        if not conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]:
            conn.executemany(
                "INSERT INTO sources (name, chat_id) VALUES (?, ?)",
                TEST_SOURCES,
            )
            print(f"Добавлено источников: {len(TEST_SOURCES)}")

        conn.commit()
    finally:
        conn.close()
    print("База готова.")


if __name__ == "__main__":
    main()
