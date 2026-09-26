"""Сверяет ручную разметку с ответами классификатора и печатает расхождения.

Запускать при активированном окружении:

    python check_classifier.py

Файл разметки — `markup.csv`, две колонки: `label` и `text`. В `label` пишем своими
глазами «заявка» или «мусор», без подсказки от фильтра. Если файла нет, скрипт создаёт
его с двумя примерами — замените их своими сообщениями из ленты.

Заявкой считается сообщение, у которого фильтр дал тип «заказ» и профиль «наш»:
именно это и есть «наше и нам подходит». Всё остальное для сверки — мусор.

Смотреть надо на два типа расхождений, и они не равны по цене:
пропущенная заявка — упущенный клиент, о котором вы никогда не узнаете;
лишний мусор в ленте — пара секунд на то, чтобы его пометить.
"""

import csv
from pathlib import Path

from classify import CLASSIFIER_PROMPT, read_answer
from filters import self_presentation_sign
from llm import ModelAnswerError, ModelUnavailable, ask_model, check_settings

MARKUP_PATH = Path(__file__).parent / "markup.csv"

EXAMPLE_ROWS = [
    ("заявка", "Нужен бот для записи клиентов: слоты, напоминания, отмена. Бюджет обсудим."),
    ("мусор", "Возьмусь за разработку ботов под ключ, мой опыт 3 года, портфолио в личке."),
]

# Столько размеченных сообщений нужно, чтобы цифра совпадений что-то значила.
MEANINGFUL_ROWS = 20


def create_example_markup():
    with MARKUP_PATH.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(("label", "text"))
        writer.writerows(EXAMPLE_ROWS)
    print(f"Создан {MARKUP_PATH.name} с двумя примерами — замените их своими сообщениями.")
    print("В колонке label: «заявка» или «мусор», своими глазами, без подсказки фильтра.")


def read_markup():
    with MARKUP_PATH.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    marked = []
    for number, row in enumerate(rows, start=2):
        label = (row.get("label") or "").strip().lower()
        text = (row.get("text") or "").strip()
        if not text:
            continue
        if label not in ("заявка", "мусор"):
            print(f"строка {number}: непонятная разметка {label!r}, пропускаю")
            continue
        marked.append((label, text))
    return marked


def only_examples(marked):
    """В файле остались только строки-примеры, которые скрипт положил сам."""
    return bool(marked) and set(marked) <= {(label, text) for label, text in EXAMPLE_ROWS}


def explain_empty_markup():
    print(f"В {MARKUP_PATH.name} пока только строки-примеры — сверять не с чем, и я не считаю.")
    print("Замените их своими сообщениями из ленты: в колонке label — «заявка» или «мусор»,")
    print("своими глазами, без подсказки фильтра.")
    print(
        f"\nЧтобы цифра совпадений что-то значила, разметьте хотя бы {MEANINGFUL_ROWS} сообщений."
    )
    print("И обязательно включите настоящие заявки, а не только мусор: на выборке из одного")
    print("мусора проверка покажет лишь то, что фильтр отсекает мусор, и ничего не скажет")
    print("про пропущенные заявки — а это и есть худшая из двух ошибок.")


def filter_verdict(text):
    """Что скажет про этот текст наш фильтр целиком — дешёвый слой плюс модель."""
    if self_presentation_sign(text):
        return "мусор", "предложение услуг", "не наш"
    answer = ask_model(CLASSIFIER_PROMPT, text)
    ai_type, ai_profile, _ = read_answer(answer)
    verdict = "заявка" if (ai_type == "заказ" and ai_profile == "наш") else "мусор"
    return verdict, ai_type, ai_profile


def main():
    if not MARKUP_PATH.exists():
        create_example_markup()
        return

    marked = read_markup()
    if not marked:
        print(f"В {MARKUP_PATH.name} нет размеченных строк.")
        return

    if only_examples(marked):
        explain_empty_markup()
        return

    check_settings()
    print(f"Сверяю {len(marked)} размеченных сообщений.")
    if len(marked) < MEANINGFUL_ROWS:
        print(
            f"Это меньше {MEANINGFUL_ROWS} — цифра ниже предварительная: на такой выборке "
            "одно случайное расхождение меняет картину целиком."
        )
    print()

    agreed = 0
    missed_requests = []
    extra_noise = []

    for label, text in marked:
        try:
            verdict, ai_type, ai_profile = filter_verdict(text)
        except (ModelUnavailable, ModelAnswerError) as error:
            print(f"  не удалось проверить: {error}")
            continue

        if verdict == label:
            agreed += 1
        elif label == "заявка":
            missed_requests.append((text, ai_type, ai_profile))
        else:
            extra_noise.append((text, ai_type, ai_profile))

    print(f"Совпало: {agreed} из {len(marked)}")
    print(f"Пропущенные заявки (я сказал «заявка», фильтр — «мусор»): {len(missed_requests)}")
    print(f"Лишний мусор (я сказал «мусор», фильтр — «заявка»): {len(extra_noise)}")

    if missed_requests:
        print("\n=== пропущенные заявки — это худшая из двух ошибок ===")
        for text, ai_type, ai_profile in missed_requests:
            print(f"  [{ai_type} / {ai_profile}] {text[:120]}")

    if extra_noise:
        print("\n=== лишний мусор ===")
        for text, ai_type, ai_profile in extra_noise:
            print(f"  [{ai_type} / {ai_profile}] {text[:120]}")

    if missed_requests or extra_noise:
        print("\nПравьте промпт классификатора в classify.py и прогоните эту сверку снова.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Остановлено.")
