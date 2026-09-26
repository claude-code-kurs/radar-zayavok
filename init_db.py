"""Создаёт таблицу заявок и наполняет её тестовыми данными.

Запускать один раз:

    python init_db.py
"""

from db import connect

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    text              TEXT NOT NULL,
    author            TEXT,
    source            TEXT,
    source_message_id TEXT,
    message_url       TEXT,
    created_at        TEXT,
    ai_label          TEXT,
    ai_reason         TEXT,
    status            TEXT DEFAULT 'новое'
)
"""

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
        conn.execute(SCHEMA)

        # Тестовые заявки добавляем только в пустую таблицу: скрипт можно запускать
        # повторно, и от второго запуска в базе не должно появиться их вдвое больше.
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

        conn.commit()
    finally:
        conn.close()
    print("База готова.")


if __name__ == "__main__":
    main()
