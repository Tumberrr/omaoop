import asyncio
import sqlite3
from database import which_rank_telegram
from sqlite3 import connect

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from aiogram.client.session.aiohttp import AiohttpSession


TOKEN = "8519811887:AAFql9ABfq93dU53muvlloRy33T9P7HvZRU"

dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: Message):

    await message.answer("Привет! Бот работает!")


@dp.message(Command("rank"))
async def ping(message: Message):


    db = connect('db/exp.db')

    c = db.cursor()
    c.execute("""
    SELECT * FROM EXPERIENCE_TELEGRAM ORDER BY experience
    """)
    data_telegram = c.fetchall()
    print(data_telegram)
    answer_telegram = ''
    for x in data_telegram:
        answer_telegram = f"Пользователь {x[1]} имеет {x[2]} EXP; Ранг: {x[3]}" + "\n" + answer_telegram
    answer_telegram = f"Рейтинг Телеграмм \n" + answer_telegram
    await message.answer(answer_telegram)
    db.commit()
    db.close()



@dp.message(F.text)
async def add_exp(message: Message):
    user_id = message.from_user.id
    user_name = message.from_user.username
    experience = 0


    db = sqlite3.connect('db/exp.db')
    c = db.cursor()
    c.execute("SELECT 1 FROM experience_telegram WHERE user_id = ? LIMIT 1", (user_id,))
    result = c.fetchone()

    if result:
        print('Данный айди уже в базе данных')


    c.execute("""
        INSERT INTO experience_telegram (user_id, user_name, experience)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id)
        DO UPDATE SET
            experience = experience + excluded.experience,
            user_name = excluded.user_name
    """, (user_id, user_name, experience))
    c.execute("SELECT * FROM experience_telegram")
    print(c.fetchall())






    c.execute("""
    UPDATE experience_telegram
    SET experience = experience + ?
    WHERE user_id = ?
    """, (9, user_id,))


    db.commit()
    db.close()

    which_rank_telegram(user_id)



async def main():

    # Подключение aiogram к локальному Xray SOCKS5
    session = AiohttpSession(
        proxy="socks5://127.0.0.1:1080"
    )

    bot = Bot(
        token=TOKEN,
        session=session
    )


    print("Бот запущен!")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)

    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())