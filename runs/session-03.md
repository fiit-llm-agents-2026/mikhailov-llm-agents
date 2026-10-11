# Сессия 3 — create_agent, middleware, проектирование инструментов

**Инструменты**:

- `food_check(product_name)` — все три признака продукта одним вызовом; промах возвращает список известных продуктов
- `food_search(gluten_free, lactose_free, vegan)` — фильтр по базе; `None` (флаг не передан) = «неважно», `True`/`False` = точное значение
- `food_rnd_basket(n)` — `n` случайных продуктов

**Middleware:** `wrap_tool_call` `log_tool_call` печатает имя и аргументы каждого вызова.

---

## Схемы инструментов (как их видит модель)

```json
{
  "type": "function",
  "function": {
    "name": "food_search",
    "description": "Search for products based on gluten and lactose free criteria.",
    "parameters": {
      "properties": {
        "gluten_free": {
          "anyOf": [
            {
              "type": "boolean"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Whether the product should be gluten-free."
        },
        "lactose_free": {
          "anyOf": [
            {
              "type": "boolean"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Whether the product should be lactose-free."
        },
        "vegan": {
          "anyOf": [
            {
              "type": "boolean"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "Whether the product should be vegan."
        }
      },
      "type": "object"
    }
  }
}
{
  "type": "function",
  "function": {
    "name": "food_check",
    "description": "Check the gluten and lactose free and vegan status of a product.",
    "parameters": {
      "properties": {
        "product_name": {
          "description": "The name of the product to check.",
          "type": "string"
        }
      },
      "required": [
        "product_name"
      ],
      "type": "object"
    }
  }
}
{
  "type": "function",
  "function": {
    "name": "food_rnd_basket",
    "description": "Return n random products.",
    "parameters": {
      "properties": {
        "n": {
          "description": "How many products to return.",
          "type": "integer"
        }
      },
      "required": [
        "n"
      ],
      "type": "object"
    }
  }
}
```

---

## Диалог с трейсом

**Вопрос:** `I avoid gluten and lactose. Can I eat oat milk? If not, what else can I eat?`

Лог middleware:

```
[tool] food_search({'gluten_free': True, 'lactose_free': True})
[tool] food_check({'product_name': 'oat milk'})
```

Транскрипт:

```
================================ Human Message =================================

I avoid gluten and lactose. Can I eat oat milk? If not, what else can I eat?
================================== Ai Message ==================================

I'll check the status of oat milk for you and search for alternatives.
Tool Calls:
  food_check (call_53d98d7da2a74b6dabf5b698)
 Call ID: call_53d98d7da2a74b6dabf5b698
  Args:
    product_name: oat milk
  food_search (call_a9f18a9ff4424898b75b9aea)
 Call ID: call_a9f18a9ff4424898b75b9aea
  Args:
    gluten_free: True
    lactose_free: True
================================= Tool Message =================================
Name: food_check

oat milk: gluten-free: False lactose-free: True vegan: True
================================= Tool Message =================================
Name: food_search

buckwheat, quinoa, millet, amaranth, teff, sorghum, tapioca, cassava flour, arrowroot, chickpea flour, polenta, corn tortilla, rice noodles, glass noodles, rice paper, tamari, psyllium husk, sago, parmesan, lactose-free milk, almond milk
================================== Ai Message ==================================

Here's what I found:

**Oat milk:** ❌ Not safe for you. It is lactose-free and vegan, but **not gluten-free** — so you should avoid it given your gluten restriction.

**Alternatives you can eat** (gluten-free and lactose-free):
- **Milk substitutes:** almond milk, lactose-free milk
- **Gluten-free grains/flours:** buckwheat, quinoa, millet, amaranth, teff, sorghum, tapioca, cassava flour, arrowroot, chickpea flour, polenta, rice noodles, glass noodles, rice paper, sago
- **Other:** corn tortilla, tamari, psyllium husk, parmesan

Would you like me to check any specific product among these for you?
```

---

## Самый дорогой вызов

Счётчики из трейса и фактическое списание Polza (`response_metadata.token_usage.cost_rub`):

| Вызов модели | input | из них из кеша | output | списано |
|---|---|---|---|---|
| 1 — выбор инструментов | 600 | 0 | 103 | **0,01986 ₽** |
| 2 — ответ пользователю | 807 | 640 | 163 | 0,01653 ₽ |
| **Итого** | 1407 | 640 | 266 | **0,03639 ₽** |

По токенам больше второй вызов: на вход ему уходит вся история заново — системный промпт, три схемы, вопрос,
ответ модели с двумя `tool_calls` и оба результата инструментов (длиннее всего список `food_search`).
Но **дороже по деньгам первый**: 640 токенов входа второго вызова — тот же префикс, что уже отправлялся в первом,
провайдер взял его из кеша по сниженной цене, и по полной второй вызов оплатил только 167 новых токенов.

---

## Стоимость

По прайсу Polza для `deepseek/deepseek-v4.1-flash` (от 10,7 ₽ / 1M входных, от 21,41 ₽ / 1M выходных)
прогон стоит 1407 × 10,7 / 10⁶ + 266 × 21,41 / 10⁶ ≈ 0,0208 ₽, а фактически списано 0,0364 ₽ — в 1,75 раза больше,
потому что в прайсе указана минимальная цена «от», а запрос ушёл к более дорогому провайдеру; скидка за кеш
в прайсе не указана, но видна в фактических суммах (второй вызов при большем числе токенов обошёлся дешевле первого).

---

## Трейс Langfuse

Выгрузка из UI Langfuse: [trace-cbb13b57758b7ae82f2f62a10f4891bf.json](traces/trace-session-3.json)
