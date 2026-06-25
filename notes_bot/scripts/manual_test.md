# Manual test: contextual notes bot

## Scenario A: workout append

1. Send: `Сегодня жим 70 на 8`
2. Check: a `workout_log` item is created.
3. Send: `Добавь в тренировку тягу блока 65 на 12`
4. Check: the same workout item is updated.
5. Check: `item_events` contains `appended`.
6. Check: `obsidian_vault/Daily/YYYY-MM-DD.md` contains both exercises inside the bot-generated block.

## Scenario B: food append

1. Send: `Съел гречку с курицей`
2. Check: a `food_log` item is created.
3. Send: `Добавь туда 2 яйца`
4. Check: the food item is updated. If today has exactly one food item, the bot should choose it automatically.

## Scenario C: task update

1. Send: `Завтра купить магний`
2. Check: a task is created with tomorrow due date.
3. Send: `Магний не завтра, а сегодня`
4. Check: the due date changes to today.
5. Check: `item_events` contains `updated`.

## Scenario D: clarification

1. Create at least two plausible target items.
2. Send: `Добавь туда 2 яйца`
3. If context is ambiguous, the bot asks a clarification question with inline buttons.
4. Pick a target item.
5. Check: the selected item is updated.

## Useful commands

- `/context`
- `/today`
- `/food`
- `/workout`
- `/tasks`
- `/rebuild_today`
- `/export_today`
