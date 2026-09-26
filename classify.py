"""Размечает собранные сообщения: дешёвый слой, потом модель.

Запускать при активированном окружении:

    python classify.py

Что делает за один запуск:
1. Считает, сколько записей ждут разметки, и говорит прикидку расхода — до первого
   запроса к модели, чтобы решение «запускать или нет» принимали вы, а не счёт.
2. Берёт не больше MAX_RECORDS_PER_RUN записей: первый запуск идёт по промпту, который
   вы ещё не видели в деле.
3. Самопрезентации отсеивает сама, без обращения к модели.
4. Остальное отправляет модели и сохраняет ответ в ai_type, ai_profile и ai_reason.

Уже размеченные записи в модель не уходят: иначе правка промпта означала бы повторную
оплату всего, что уже оплачено.
"""

from db import average_text_length, count_unclassified, get_unclassified, set_ai_result
from filters import self_presentation_sign
from llm import ModelAnswerError, ModelUnavailable, ask_model, check_settings
from settings import (
    CHARS_PER_TOKEN,
    MAX_RECORDS_PER_RUN,
    SELF_PRESENTATION_REASON,
)

# Промпт классификатора. Две оси вместо одной метки: «что это» и «наше ли оно».
# Смешивать их в одно слово нельзя — модель начнёт отвечать то на первый вопрос,
# то на второй, и одинаковые по форме объявления получат разные метки.
CLASSIFIER_PROMPT = """Ты классификатор сообщений из Telegram-групп, где ищут исполнителей.

На входе — текст одного сообщения. Оцени его по двум осям независимо.

Ось «тип» — что это за сообщение:
- "заказ" — человек ищет исполнителя на конкретную работу;
- "вакансия" — берут сотрудника в команду, в штат или на постоянную занятость;
- "предложение услуг" — исполнитель предлагает себя, резюме, портфолио, реклама услуг;
- "другое" — всё остальное: обсуждения, вопросы, объявления не по теме, спам.

Ось «профиль» — наша ли это тема, то есть разработка ботов, парсеров, интеграций и
другой автоматизации:
- "наш" — работа по этому профилю;
- "не наш" — работа по другому профилю, даже если сообщение по форме похоже.

Отвечай строго одним объектом JSON с тремя полями и ничем больше:
{"type": "заказ|вакансия|предложение услуг|другое", "profile": "наш|не наш", "reason": "короткая причина решения, одно предложение"}

Никакого текста вне JSON: ни пояснений до, ни после, ни обрамления блоком кода."""

ALLOWED_TYPES = ("заказ", "вакансия", "предложение услуг", "другое")
ALLOWED_PROFILES = ("наш", "не наш")

# Пометка для записи, ответ по которой не удалось разобрать. Такая запись больше не
# уходит в модель: иначе платили бы за неё каждый прогон заново.
UNCHECKED = "не проверено ИИ"


def estimate_tokens(records_count, average_length):
    """Грубая прикидка расхода на весь заход, в токенах.

    Считаем по средней длине текста, потому что точность здесь не нужна: нужен порядок
    величины. На живом прогоне выходило около 700 токенов на запись.
    """
    prompt_tokens = len(CLASSIFIER_PROMPT) / CHARS_PER_TOKEN
    answer_tokens = 60
    per_record = prompt_tokens + average_length / CHARS_PER_TOKEN + answer_tokens
    return int(per_record * records_count)


def read_answer(answer):
    """Достаёт из ответа модели тип, профиль и причину, проверяя допустимые значения."""
    ai_type = str(answer.get("type", "")).strip().lower()
    ai_profile = str(answer.get("profile", "")).strip().lower()
    reason = str(answer.get("reason", "")).strip()
    if ai_type not in ALLOWED_TYPES:
        raise ModelAnswerError(f"неизвестный тип: {ai_type!r}")
    if ai_profile not in ALLOWED_PROFILES:
        raise ModelAnswerError(f"неизвестный профиль: {ai_profile!r}")
    return ai_type, ai_profile, reason


def main():
    check_settings()

    waiting = count_unclassified()
    if not waiting:
        print("Размечать нечего: у всех записей уже есть оценка ИИ.")
        return

    average_length = average_text_length()
    take = min(waiting, MAX_RECORDS_PER_RUN)
    print(f"Ждут разметки: {waiting} записей, средняя длина текста {average_length} знаков.")
    print(f"За этот запуск размечаем {take} — примерно {estimate_tokens(take, average_length)} токенов.")
    if waiting > take:
        print(
            f"Остальные {waiting - take} останутся на следующий запуск: посмотрите на качество "
            "разметки и на расход, прежде чем гнать всё."
        )

    records = get_unclassified(take)
    by_cheap_layer = 0
    by_model = 0
    unchecked = 0
    untouched = 0

    for row in records:
        sign = self_presentation_sign(row["text"])
        if sign:
            # В модель не отправляем вовсе: это предложение услуг, и видно это без неё.
            set_ai_result(
                row["id"],
                "предложение услуг",
                "не наш",
                f"{SELF_PRESENTATION_REASON}: {sign}",
            )
            by_cheap_layer += 1
            continue

        try:
            answer = ask_model(CLASSIFIER_PROMPT, row["text"])
            ai_type, ai_profile, reason = read_answer(answer)
        except ModelUnavailable as error:
            # Виноват канал связи, а не данные: запись не трогаем, следующий прогон её подберёт.
            print(f"  id={row['id']}: модель недоступна ({error}) — запись оставлена как была")
            untouched += 1
            continue
        except ModelAnswerError as error:
            # Виновата модель: формат не тот. Помечаем и идём дальше, не роняя весь прогон.
            set_ai_result(row["id"], UNCHECKED, "", f"ответ модели не разобран: {error}")
            unchecked += 1
            continue

        set_ai_result(row["id"], ai_type, ai_profile, reason)
        by_model += 1

    print(
        f"\nГотово. Отсеяно дешёвым слоем: {by_cheap_layer}, размечено моделью: {by_model}."
    )
    if unchecked:
        print(f"Не проверено ИИ (ответ не разобран): {unchecked}")
    if untouched:
        print(f"Оставлено без изменений из-за сбоев связи: {untouched} — запустите позже")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Остановлено.")
