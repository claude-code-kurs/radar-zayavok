"""Пароль кабинета и подпись cookie входа.

Пароль нигде не хранится в открытом виде: в `.env` лежит только его хеш.
Чтобы получить строку для `.env`, запустить:

    python auth.py "пароль"
"""

import hashlib
import hmac
import secrets

COOKIE_NAME = "cabinet_session"
ITERATIONS = 200000


def hash_password(password, salt=None):
    """Возвращает строку вида pbkdf2_sha256$итерации$соль$хеш."""
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), ITERATIONS
    ).hex()
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest}"


def check_password(password, stored):
    """Сверяет введённый пароль с хешем из `.env`."""
    try:
        algorithm, iterations, salt, digest = stored.split("$")
    except (AttributeError, ValueError):
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations)
    ).hex()
    return hmac.compare_digest(candidate, digest)


def make_session(login, secret):
    """Значение cookie: логин и его подпись секретом из `.env`."""
    signature = hmac.new(secret.encode("utf-8"), login.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{login}:{signature}"


def check_session(value, secret):
    """Проверяет, что cookie подписана нашим секретом, а не подделана."""
    if not value or ":" not in value:
        return False
    login, signature = value.rsplit(":", 1)
    expected = hmac.new(secret.encode("utf-8"), login.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print('Использование: python auth.py "пароль"')
    else:
        print(f"CABINET_PASSWORD_HASH={hash_password(sys.argv[1])}")
