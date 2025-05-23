import os
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
import openai
from story import story  # <-- подключаем твой story.py

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# Хранилище состояния каждого пользователя
user_states = {}  # user_id -> scene_id

# Получить текущую сцену пользователя
def get_scene(user_id):
    return user_states.get(user_id, "ep1_intro")

# Получить следующую сцену
def next_scene(scene_id):
    return story.get(scene_id, {}).get("next")

# Генерация ответа от имени персонажей на основе целей
def gpt_reply(characters, goals, scene_text, user_input):
    characters_list = ", ".join(characters)
    goals_text = "\n".join([f"{char}: {goal}" for char, goal in goals.items()])

    prompt = f"""
Ты — один из персонажей интерактивной хоррор-истории. Алекс — главная героиня, пользователь управляет её действиями.

Сцена: "{scene_text}"
Пользователь (Алекс) пишет: "{user_input}"

Вот доступные персонажи и их цели:
{goals_text}

Ответь от имени одного из персонажей (кто логичнее), как будто вы переписываетесь в мессенджере.
Формат: "Имя: сообщение"
Пример: "Итан: Я пойду с тобой, если хочешь."
"""

    response = openai.Completion.create(
        model="text-davinci-003",
        prompt=prompt,
        temperature=0.8,
        max_tokens=200,
    )
    return response.choices[0].text.strip()

# Команда /start
def start(update: Update, context: CallbackContext):
    user_id = update.message.chat_id
    user_states[user_id] = "ep1_intro"
    scene = story["ep1_intro"]
    update.message.reply_text(scene["text"], reply_markup=ReplyKeyboardMarkup([["Продолжить"]], resize_keyboard=True))

# Обработка сообщений
def handle_message(update: Update, context: CallbackContext):
    user_id = update.message.chat_id
    user_input = update.message.text.strip()
    scene_id = get_scene(user_id)
    scene = story.get(scene_id)

    if not scene:
        update.message.reply_text("Что-то пошло не так. Попробуйте позже.")
        return

    # Переход на следующую сцену по кнопке "Продолжить"
    if user_input.lower() == "продолжить" and scene.get("next"):
        next_id = scene["next"]
        user_states[user_id] = next_id
        next_scene_data = story[next_id]
        update.message.reply_text(next_scene_data["text"], reply_markup=ReplyKeyboardMarkup([["Продолжить"]], resize_keyboard=True))
        return

    # Генерация ответа от персонажа
    characters = scene.get("characters", [])
    goals = scene.get("goals", {})
    reply = gpt_reply(characters, goals, scene["text"], user_input)
    update.message.reply_text(reply)

# Точка входа
def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    updater.start_polling()
    updater.idle()
if __name__ == "__main__":
    main()
