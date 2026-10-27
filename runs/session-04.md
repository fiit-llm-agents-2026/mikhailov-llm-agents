# Сессия 4 — контекст и краткосрочная память

**Чекпоинтер:** `SqliteSaver`, файл `product.db` (`*.db` и `*.db-*` в `.gitignore`)
**Тред:** `thread_id` в `config` на каждом `invoke`, в `invoke` уходит только новое сообщение
**Техника:** `SummarizationMiddleware(trigger=("messages", 15), keep=("messages", 8))`
**Запуск:** `python agent.py --thread-id <id> --memory summary|buffer`
**Нагрузка:** `load_test.py` — 50 реплик, контекст и `input_tokens` каждого вызова модели

**Модель:** `MODEL_CHEAP` из `.env`, она же пишет резюме

Почему суммаризация, а не окно: ограничения пользователя (без глютена, без лактозы, веган)
звучат в первом ходе и нужны в каждом следующем. Скользящее окно первым выбрасывает
именно начало, а резюме его сохраняет.

---

## Рестарт

Процесс 1, `python agent.py --thread-id restart-demo`:

```
you> Hi! I avoid gluten and lactose, and I am vegan.
[tool] food_search({'gluten_free': True})
[tool] food_search({'vegan': True})
[tool] food_search({'lactose_free': True})
[tool] food_search({'gluten_free': True, 'lactose_free': True, 'vegan': True})
agent> Here are the products that meet **all three** of your dietary requirements — gluten-free, lactose-free, and vegan:
...
[state] 8 messages, ~732 tokens
you> Can I eat bread?
[tool] food_check({'product_name': 'bread'})
agent> Unfortunately, **no** — you can't eat bread as it is.

Here's the breakdown for bread:
- **Gluten-free:** ❌ No
- **Lactose-free:** ❌ No
- **Vegan:** ✅ Yes
...
[state] 12 messages, ~948 tokens
you> exit
```

Процесс 2, новый запуск с тем же `--thread-id restart-demo`:

```
you> What are my dietary restrictions? Answer from our conversation.
agent> Based on our conversation, your dietary restrictions are:

1. **Gluten-free** — you avoid gluten
2. **Lactose-free** — you avoid lactose
3. **Vegan** — you avoid animal products
[state] 14 messages, ~1041 tokens
```

Второй процесс ни разу не видел первого сообщения, но ответил верно: 12 сообщений
поднялись из `product.db`, к ним добавились вопрос и ответ — получилось 14.

---

## 50 ходов: полный буфер vs суммаризация

Один и тот же сценарий из 50 реплик, треды `load-buffer` и `load-summary`. Ограничения
названы в ходе 1, ход 50 спрашивает их обратно.

| | буфер | суммаризация |
|---|---|---|
| input за 50 ходов | 783 823 | **264 880** |
| output за 50 ходов | 10 469 | 41 935 |
| вызовов модели | 97 | 125 |
| срабатываний суммаризации | 0 | 29 |
| контекст после хода 50 | ~14 017 | ~1 830 |
| сообщений в треде после хода 50 | 227 | 14 |
| ход 50: назвал ограничения | да | да |

По ходам (контекст — `count_tokens_approximately` по system + state после хода, input —
сумма `usage_metadata.input_tokens` всех вызовов хода, S — сработала суммаризация):

| ход | контекст, буфер | контекст, суммаризация | input, буфер | input, суммаризация |
|---|---|---|---|---|
| 1 | 2 199 | 405 | 3 810 | 1 357 |
| 5 | 3 035 | 1 200 | 6 335 | 3 041 |
| 10 | 4 984 | 1 480 | 9 948 | 5 115 S |
| 15 | 6 237 | 1 702 | 12 881 | 6 223 S |
| 20 | 7 539 | 1 578 | 15 451 | 6 275 S |
| 25 | 8 376 | 1 526 | 17 029 | 4 125 |
| 30 | 9 289 | 1 664 | 18 710 | 2 183 |
| 35 | 10 193 | 1 922 | 10 333 | 7 611 S |
| 40 | 11 856 | 2 686 | 11 868 | 8 655 S |
| 45 | 13 063 | 1 709 | 26 491 | 7 196 S |
| 50 | 14 017 | 1 830 | 14 169 | 2 350 |

---

## Что показывают цифры

Буфер растёт линейно и к ходу 50 таскает ~14k токенов. Хуже всего ходы с инструментом:
модель вызывается два-три раза, и каждый раз получает весь тред заново — отсюда 26 491 и
41 669 входных токенов на ходах 45 и 48. С суммаризацией контекст держится в коридоре
1,2–2,7k, а входных токенов за прогон втрое меньше.

Экономия не бесплатная: 28 лишних вызовов модели и вчетверо больше output — резюме пишет
та же модель. Порог `("messages", 15)` при `keep=8` оказался слишком низким: ход с
инструментом добавляет 4–7 сообщений, и суммаризация срабатывала почти через ход, 29 раз
из 50. Порог выше или по токенам дал бы ту же экономию за меньшее число вызовов.

Главное — факты из хода 1 пережили 29 перезаписей резюме: в ходе 50 агент назвал все три
ограничения.

---

## Трейс со срабатыванием суммаризации

Ход 4 треда `load-summary`, вопрос `Is buckwheat ok for me?`:

```
LangGraph
├─ SummarizationMiddleware.before_model     13 сообщений, порог не пройден
├─ model → ChatOpenAI                        input 1370
├─ tools → food_check
├─ SummarizationMiddleware.before_model     порог пройден
│  └─ ChatOpenAI                             input 979 — пишет резюме
└─ model → ChatOpenAI                        input 1390
```

Первая проверка пропускает, модель зовёт `food_check`, тред дорастает до порога — и перед
вторым вызовом модели middleware сворачивает голову треда в резюме.

---

## Трейс Langfuse

Выгрузка из Langfuse: [trace-bf5276442b4628bb85c8ff34228f79d1.json](traces/trace-session-4.json)
Публичный ключ Langfuse в выгрузке заменён на `pk-lf-REDACTED`.
