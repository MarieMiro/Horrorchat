import os
from flask import Flask, request
from dotenv import load_dotenv
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters
from openai import OpenAI
from story import story

# Загрузка переменных окружения
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Инициализация клиентов
client = OpenAI(api_key=OPENAI_API_KEY)
app = Flask(__name__)
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dispatcher = Dispatcher(bot, None, use_context=True)

# Состояния пользователей
user_states = {}  # user_id -> {scene_id, step_index}

def get_state(user_id):
    return user_states.get(user_id, {"scene": "ep1_intro", "step": 0})

def update_state(user_id, scene_id, step_index):
    user_states[user_id] = {"scene": scene_id, "step": step_index}

# Ответ GPT
def gpt_reply(characters, goals, scene_text, user_input):
    goals_text = "\n".join([f"{char}: {goal}" for char, goal in goals.items()])
    system_prompt = f"""
Ты — персонаж из хоррор-истории. Алекс — главная героиня, игрок пишет от её имени.

Контекст сцены:
{scene_text}

Цели персонажей:
{goals_text}

Ответь коротко, в формате живого диалога от лица других персонажей. Реплики могут быть с юмором или обеспокоенные. Не пиши от имени Алекс.

Пример:
Майкл: Мы почти приехали.
Джессика: Смотрите, какой странный знак!
    """

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ],
            temperature=0.7,
            max_tokens=300
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print("GPT ERROR:", e)
        return f"Ошибка GPT: {str(e)}"

# /start
def start(update, context):
    user_id = update.message.chat_id
    update_state(user_id, "ep1_intro", 0)
    intro_text = story["ep1_intro"]["steps"][0]["text"]
    update.message.reply_text(intro_text)

    # Показываем первые реплики из первого шага
    characters = story["ep1_intro"]["steps"][0].get("characters", [])
    for char in characters:
        update.message.reply_text(f'{char["name"]}: {char["line"]}')

    # Переход к следующему шагу
    update_state(user_id, "ep1_intro", 1)

# handle user input
def handle_message(update, context):
    user_id = update.message.chat_id
    user_input = update.message.text.strip()

    state = get_state(user_id)
    scene_id = state["scene"]
    step_index = state["step"]
    scene = story.get(scene_id)

    if not scene:
        update.message.reply_text("Произошла ошибка.")
        return

    # Ответ пользователю
    goals = scene.get("goals", {})
    scene_text = scene["steps"][step_index - 1]["text"] if step_index > 0 else ""
    gpt_response = gpt_reply([], goals, scene_text, user_input)
    for line in gpt_response.split("\n"):
        line = line.strip()
        if line:
            update.message.reply_text(line)

    # Продолжение по сценарию
    if step_index < len(scene["steps"]):
        step = scene["steps"][step_index]
        if "text" in step:
            update.message.reply_text(step["text"])
        for char in step.get("characters", []):
            update.message.reply_text(f'{char["name"]}: {char["line"]}')
        update_state(user_id, scene_id, step_index + 1)
    else:
        update.message.reply_text("Конец сцены.")

# Webhook
@app.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "ok"

# Хендлеры
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

# Запуск сервера
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
