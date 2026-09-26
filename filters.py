"""Отбор сообщений: ключевые слова и защита от повторов по содержимому.

Отдельный файл, потому что это единственная часть сбора, которую можно проверить
без Telegram: на входе текст, на выходе решение.
"""

import hashlib
import re

from settings import (
    KEYWORDS,
    NEAR_DUPLICATE_MIN_WORDS,
    NEAR_DUPLICATE_RATIO,
    TAIL_MARKERS,
)

# Ссылки, упоминания и разметка — всё, что не несёт смысла при сравнении текстов.
LINK_RE = re.compile(r"https?://\S+|t\.me/\S+")
MENTION_RE = re.compile(r"@\w+")
# Оставляем только буквы, цифры и пробелы: пунктуация и эмодзи уходят вместе.
KEEP_RE = re.compile(r"[^\w\s]", re.UNICODE)
SPACES_RE = re.compile(r"\s+")


def clean_text(text):
    """Убирает markdown-разметку, которую Telethon возвращает в тексте сообщения.

    Нужно до сравнения с ключевыми словами: звёздочки и подчёркивания приклеиваются
    к словам и портят сравнение.
    """
    if not text:
        return ""
    return SPACES_RE.sub(" ", re.sub(r"[*_`~]", "", text)).strip()


def strip_service_tail(text):
    """Отрезает служебную приписку канала — всё, начиная с фразы-маркера.

    Приписку не храним и нигде не учитываем: источник и ссылка на сообщение у нас лежат
    в своих полях, а в тексте этот хвост только мешает — и отсеву, и сравнению.
    """
    if not text:
        return ""
    lowered = text.lower()
    cut_at = len(text)
    for marker in TAIL_MARKERS:
        position = lowered.find(marker.lower())
        if position != -1:
            cut_at = min(cut_at, position)
    return text[:cut_at].strip()


def prepare_text(text):
    """Готовит текст сообщения к работе. Порядок шагов здесь и есть главное.

    Сначала снимаем разметку, потом отрезаем служебную приписку канала — и только
    потом текст идёт на словарный отсев, на хеш и на сравнение с уже записанными.
    Если приписку убрать позже отсева, словарь будет совпадать с ней, а не с заявкой.
    """
    return strip_service_tail(clean_text(text))


def normalize_text(text):
    """Приводит текст к виду, в котором его можно сравнивать с другими текстами."""
    lowered = clean_text(text).lower()
    without_links = MENTION_RE.sub(" ", LINK_RE.sub(" ", lowered))
    letters_only = KEEP_RE.sub(" ", without_links)
    return SPACES_RE.sub(" ", letters_only).strip()


def content_hash(text):
    """Хеш нормализованного текста — по нему видно точный повтор объявления."""
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def matched_keywords(text):
    """Какие ключевые слова совпали. Пустой список значит «не прошло отсев».

    Совпадение считаем только с начала слова, иначе «бот» найдётся внутри «работа».
    """
    words = normalize_text(text).split()
    matched = []
    for keyword in KEYWORDS:
        if any(word.startswith(keyword) for word in words):
            matched.append(keyword)
    return matched


def is_near_duplicate(text, known_texts):
    """Похоже ли сообщение на одно из уже записанных — то же объявление с мелкой правкой.

    Доля общих слов считается от более длинного из двух текстов: так добавленная
    строчка «up, актуально» не превращает повтор в новое объявление.

    На коротких текстах проверка выключена: «нужен бот для записи, оплата 5000» и
    «нужен бот для рассылки, оплата 5000» — разные заказы с почти одинаковыми словами.
    """
    words = set(normalize_text(text).split())
    if len(words) < NEAR_DUPLICATE_MIN_WORDS:
        return False

    for known in known_texts:
        known_words = set(normalize_text(known).split())
        if len(known_words) < NEAR_DUPLICATE_MIN_WORDS:
            continue
        common = len(words & known_words)
        ratio = common / max(len(words), len(known_words))
        if ratio >= NEAR_DUPLICATE_RATIO:
            return True
    return False
