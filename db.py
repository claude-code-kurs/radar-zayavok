"""Работа с базой: заявки и источники."""

import sqlite3
from pathlib import Path

# Запись считается неразмеченной, пока в ai_type ничего нет. Пометка «не проверено ИИ»
# тоже считается разметкой: такая запись в модель больше не уходит.
UNCLASSIFIED = "ai_type IS NULL OR ai_type = ''"

DB_PATH = Path(__file__).parent / "radar.db"


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_requests():
    """Все заявки для ленты кабинета, сначала самые свежие."""
    conn = connect()
    try:
        return conn.execute(
            """
            SELECT id, text, author, source, created_at, ai_type, ai_profile, ai_reason
            FROM requests
            ORDER BY created_at DESC
            """
        ).fetchall()
    finally:
        conn.close()


def count_unclassified():
    """Сколько записей ждут разметки — нужно до первого запроса к модели, чтобы
    понимать объём и расход заранее."""
    conn = connect()
    try:
        return conn.execute(f"SELECT COUNT(*) FROM requests WHERE {UNCLASSIFIED}").fetchone()[0]
    finally:
        conn.close()


def get_unclassified(limit):
    """Записи без оценки ИИ, начиная с самых старых, не больше указанного числа."""
    conn = connect()
    try:
        return conn.execute(
            f"SELECT id, text FROM requests WHERE {UNCLASSIFIED} ORDER BY id LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()


def average_text_length():
    """Средняя длина текста в символах — по ней прикидываем расход токенов."""
    conn = connect()
    try:
        value = conn.execute(f"SELECT AVG(LENGTH(text)) FROM requests WHERE {UNCLASSIFIED}").fetchone()[0]
        return int(value or 0)
    finally:
        conn.close()


def set_ai_result(request_id, ai_type, ai_profile, reason):
    """Сохраняет оценку ИИ: тип сообщения, профиль и причину решения."""
    conn = connect()
    try:
        conn.execute(
            "UPDATE requests SET ai_type = ?, ai_profile = ?, ai_reason = ? WHERE id = ?",
            (ai_type, ai_profile, reason, request_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_sources():
    """Список источников — он же настройки сбора: кого обходит юзербот."""
    conn = connect()
    try:
        return conn.execute(
            """
            SELECT id, name, chat_id, last_seen_at, findings_count
            FROM sources
            ORDER BY id
            """
        ).fetchall()
    finally:
        conn.close()


def set_source_chat_id(source_id, chat_id):
    """Числовой id чата узнаём только при первом подключении — запоминаем его."""
    conn = connect()
    try:
        conn.execute("UPDATE sources SET chat_id = ? WHERE id = ?", (str(chat_id), source_id))
        conn.commit()
    finally:
        conn.close()


def mark_source_seen(source_id, seen_at):
    """Когда в источнике последний раз было хоть какое-то сообщение.

    Обновляем, даже если сообщение не прошло фильтры: старая дата здесь означает, что
    источник замолчал, а не что радар сломался. Более свежую дату старой не затираем —
    строки ISO 8601 сравниваются как даты.
    """
    conn = connect()
    try:
        conn.execute(
            """
            UPDATE sources
            SET last_seen_at = ?
            WHERE id = ? AND (last_seen_at IS NULL OR last_seen_at < ?)
            """,
            (seen_at, source_id, seen_at),
        )
        conn.commit()
    finally:
        conn.close()


def add_finding_to_source(source_id):
    """Счётчик находок растёт только тогда, когда сообщение реально стало заявкой."""
    conn = connect()
    try:
        conn.execute(
            "UPDATE sources SET findings_count = findings_count + 1 WHERE id = ?",
            (source_id,),
        )
        conn.commit()
    finally:
        conn.close()


def request_exists(source_message_id):
    """Вторая линия защиты от повторов: пара «id чата и id сообщения» уже записана?"""
    conn = connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM requests WHERE source_message_id = ? LIMIT 1",
            (source_message_id,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def content_hash_exists(content_hash):
    """Третья линия: такое же по содержимому объявление уже записано?"""
    conn = connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM requests WHERE content_hash = ? LIMIT 1",
            (content_hash,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def recent_texts(limit):
    """Тексты последних записей — с ними сравниваем почти одинаковые сообщения."""
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT text FROM requests ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [row["text"] for row in rows]
    finally:
        conn.close()


def insert_request(
    text,
    author,
    source,
    source_message_id,
    message_url,
    created_at,
    matched_keywords,
    edit_date,
    content_hash,
):
    """Записывает найденную заявку. Поля ИИ и статус заполняются в следующих уроках.

    Возвращает True, если запись добавлена, и False, если такую пару «чат и сообщение»
    не пустил UNIQUE в схеме. Второе означает, что проверка перед записью повтор
    не увидела, — вызывающий это считает отдельно, а не как обычный дубль.
    """
    conn = connect()
    try:
        conn.execute(
            """
            INSERT INTO requests (
                text, author, source, source_message_id, message_url, created_at,
                matched_keywords, edit_date, content_hash,
                ai_type, ai_profile, ai_reason, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', '', 'новое')
            """,
            (
                text,
                author,
                source,
                source_message_id,
                message_url,
                created_at,
                matched_keywords,
                edit_date,
                content_hash,
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # Схема не пустила повтор. Падать посреди обхода из-за дубля нельзя — ради этого
        # уровни защиты и заводили, — поэтому сообщаем наружу и идём дальше.
        return False
    finally:
        conn.close()
