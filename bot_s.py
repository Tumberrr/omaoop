import discord
from discord.ext import commands

import requests
from bs4 import BeautifulSoup

import aiohttp
import asyncio

import yt_dlp
import os
import subprocess
import asyncio
import sys
from sqlite3 import *

import random

from database import add_exp
from database import which_rank
volume = '1'
vol_for_skip = volume
# =========================================================
# CONFIG
# =========================================================


TOKEN = os.environ.get("TOKEN")

FFMPEG_PATH = "ffmpeg"

# =========================================================
# DISCORD
# =========================================================

intents = discord.Intents.default()

intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================================================
# SONG
# =========================================================

class Song:

    def __init__(self, url: str, title: str, requester: str):
        self.url = url
        self.title = title
        self.requester = requester


# =========================================================
# AUDIO SOURCE
# =========================================================

class ProcessAudioSource(discord.AudioSource):

    def __init__(self, process):
        self.process = process

    def read(self):

        # 20 ms PCM:
        # 48000 Hz
        # 2 channels
        # 16 bit
        #
        # 48000 * 0.02 * 2 * 2 = 3840 bytes

        data = self.process.stdout.read(3840)

        if not data:
            return b""

        return data

    def is_opus(self):
        return False

    def cleanup(self):

        try:

            if self.process.poll() is None:
                self.process.kill()

        except Exception:
            pass


# =========================================================
# MUSIC PLAYER
# =========================================================

class MusicPlayer:

    def __init__(self, guild_id):

        self.guild_id = guild_id

        self.queue = asyncio.Queue()

        self.current = None

        self.voice = None

        self.text_channel = None

        self.playing = False

        self.yt_process = None

        self.ffmpeg = None

        self.source = None


# =========================================================
# PLAYERS
# =========================================================

players = {}


def get_player(guild_id):

    if guild_id not in players:
        players[guild_id] = MusicPlayer(guild_id)

    return players[guild_id]


# =========================================================
# READY
# =========================================================

@bot.event
async def on_ready():

    print("==============================")
    print(f"Бот запущен: {bot.user}")
    print("==============================")



# =========================================================
# START NEXT SONG
# =========================================================

async def play_next(guild_id, vol=volume):

    player = get_player(guild_id)

    # Бот уже ничего не играет
    player.playing = False

    # Получаем голосовой клиент
    guild = bot.get_guild(guild_id)

    if guild is None:
        return

    voice = guild.voice_client

    if voice is None:
        return

    player.voice = voice

    # =====================================================
    # ЕСЛИ ОЧЕРЕДЬ ПУСТА
    # =====================================================

    if player.queue.empty():

        player.current = None

        try:
            await player.text_channel.send(
                "📭 Очередь закончилась."
            )
        except Exception:
            pass

        return

    # =====================================================
    # БЕРЁМ СЛЕДУЮЩИЙ ТРЕК
    # =====================================================

    song = await player.queue.get()

    player.current = song
    player.playing = True

    print()
    print("==============================")
    print("НАЧИНАЕМ ТРЕК")
    print("Название:", song.title)
    print("Пользователь:", song.requester)
    print("==============================")
    print()

    try:

        # =================================================
        # YT-DLP
        # =================================================

        yt_process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "yt_dlp",
                "-f",
                "bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best",

                "--no-playlist",

                "--quiet",
                "--no-warnings",
                "--no-progress",
                "cookiefile": "cookies.txt",
                "--force-ipv4",

                "--retries",
                "10",

                "--fragment-retries",
                "10",

                "-o",
                "-",

                song.url
            ],

            stdout=subprocess.PIPE,

            # Не оставляем stderr открытым,
            # чтобы процесс не заблокировался
            stderr=subprocess.DEVNULL,

            stdin=subprocess.DEVNULL
        )

        player.yt_process = yt_process

        # =================================================
        # FFMPEG
        # =================================================

        ffmpeg = subprocess.Popen(
            [
                FFMPEG_PATH,

                "-hide_banner",
                "-loglevel",
                "error",

                "-i",
                "pipe:0",

                '-af',
                f'volume={vol}',
                "-f",
                "s16le",

                "-ar",
                "48000",

                "-ac",
                "2",

                "pipe:1"
            ],

            # yt-dlp -> FFmpeg
            stdin=yt_process.stdout,

            # FFmpeg -> Python
            stdout=subprocess.PIPE,

            stderr=subprocess.DEVNULL
        )

        player.ffmpeg = ffmpeg

        # yt-dlp больше не должен держать stdout
        yt_process.stdout.close()

        # =================================================
        # AUDIO SOURCE
        # =================================================

        source = ProcessAudioSource(ffmpeg)

        player.source = source

        # =================================================
        # AFTER
        # =================================================

        def after(error):

            print()
            print("==============================")
            print("ТРЕК ЗАКОНЧИЛСЯ")
            print("==============================")

            if error:
                print(
                    "Ошибка Discord:",
                    error
                )

            # Следующий трек нужно запускать
            # из asyncio event loop.
            asyncio.run_coroutine_threadsafe(
                finish_song(guild_id),
                bot.loop
            )

        # =================================================
        # PLAY
        # =================================================

        voice.play(
            source,
            after=after
        )

        try:

            await player.text_channel.send(
                f"▶️ Сейчас играет: **{song.title}**"
            )

        except Exception:
            pass

        print("▶️ FFmpeg запущен")

    except Exception as e:

        print()
        print("==============================")
        print("ОШИБКА PLAY NEXT")
        print(type(e).__name__, e)
        print("==============================")
        print()

        player.playing = False
        player.current = None

        try:

            await player.text_channel.send(
                f"❌ Не удалось воспроизвести:\n"
                f"`{e}`"
            )

        except Exception:
            pass

        # Пробуем следующий трек
        
        await play_next(guild_id, vol=vol_for_skip)


# =========================================================
# FINISH SONG
# =========================================================

async def finish_song(guild_id):

    player = get_player(guild_id)

    # =====================================================
    # УБИВАЕМ FFMPEG
    # =====================================================

    try:

        if (
            player.ffmpeg is not None
            and player.ffmpeg.poll() is None
        ):

            player.ffmpeg.kill()

    except Exception:
        pass

    # =====================================================
    # УБИВАЕМ YT-DLP
    # =====================================================

    try:

        if (
            player.yt_process is not None
            and player.yt_process.poll() is None
        ):

            player.yt_process.kill()

    except Exception:
        pass

    player.ffmpeg = None
    player.yt_process = None
    player.source = None
    player.current = None
    player.playing = False

    # =====================================================
    # ЗАПУСКАЕМ СЛЕДУЮЩУЮ ПЕСНЮ
    # =====================================================

    await play_next(guild_id, vol=vol_for_skip)


# =========================================================
# PLAY
# =========================================================

@bot.command()
async def play(ctx, url: str, *, vol=volume):
    try: 
        vol = int(vol)
    except: return
    vol = str(vol)

    global vol_for_skip
    vol_for_skip = vol

    # =====================================================
    # ПРОВЕРКА ГОЛОСОВОГО КАНАЛА
    # =====================================================
    if not ctx.author.voice:

        await ctx.send(
            "❌ Сначала зайди в голосовой канал."
        )

        return

    voice_channel = ctx.author.voice.channel

    # =====================================================
    # PLAYER
    # =====================================================

    player = get_player(
        ctx.guild.id
    )

    player.text_channel = ctx.channel

    # =====================================================
    # CONNECT
    # =====================================================

    voice = ctx.guild.voice_client

    if voice is None:

        voice = await voice_channel.connect()

    elif voice.channel != voice_channel:

        await voice.move_to(
            voice_channel
        )

    player.voice = voice

    # =====================================================
    # GET TITLE
    # =====================================================

    await ctx.send(
        "🔎 Получаю информацию..."
    )

    ydl_opts = {

        "quiet": True,

        "no_warnings": True,

        "noplaylist": True,

        "force_ipv4": True
    }

    try:

        loop = asyncio.get_running_loop()

        def get_info():

            with yt_dlp.YoutubeDL(
                ydl_opts
            ) as ydl:

                info = ydl.extract_info(
                    url,
                    download=False
                )

                return info.get(
                    "title",
                    "Unknown"
                )

        title = await loop.run_in_executor(
            None,
            get_info
        )

        # =================================================
        # CREATE SONG
        # =================================================

        song = Song(
            url=url,
            title=title,
            requester=ctx.author.global_name
        )

        # =================================================
        # ADD TO QUEUE
        # =================================================

        await player.queue.put(
            song
        )

        position = player.queue.qsize()

        # =================================================
        # MESSAGE
        # =================================================

        if player.playing:
            await ctx.send(
                    f"✅ Добавлено в очередь\n"
                    f"🎵 **{title}**\n"
                    f"📍 Позиция: **{position}**\n"
                    f"Громкость: {vol}"
                )
        else:

            await ctx.send(
                f"🎵 **{title}**\n"
                f"▶️ Запускаю..."
            )

        # =================================================
        # START IF NOTHING PLAYING
        # =================================================

        if not player.playing:

            await play_next(
                ctx.guild.id,
                vol
            )

    except Exception as e:

        print()
        print("==============================")
        print("ОШИБКА PLAY")
        print(type(e).__name__, e)
        print("==============================")
        print()

        await ctx.send(
            f"❌ Не удалось добавить музыку:\n"
            f"`{e}`"
        )


# =========================================================
# QUEUE
# =========================================================

@bot.command(name="queue")
async def show_queue(ctx):

    player = get_player(
        ctx.guild.id
    )

    songs = list(
        player.queue._queue
    )

    # Если ничего нет
    if not songs and player.current is None:

        await ctx.send(
            "📭 Очередь пустая."
        )

        return

    text = "🎵 **Музыкальная очередь**\n\n"

    # =====================================================
    # CURRENT
    # =====================================================

    if player.current:

        text += (
            f"▶️ **Сейчас играет:**\n"
            f"**{player.current.title}**\n\n"
        )

    # =====================================================
    # QUEUE
    # =====================================================

    if songs:

        text += "**Далее:**\n"

        for index, song in enumerate(
            songs,
            start=1
        ):

            text += (
                f"`{index}.` "
                f"**{song.title}**\n"
            )

    else:

        text += "📭 Больше песен нет."

    await ctx.send(text)


# =========================================================
# SKIP
# =========================================================

@bot.command()
async def skip(ctx):
    guild_id = ctx.guild.id

    player = get_player(
        ctx.guild.id
    )

    voice = ctx.guild.voice_client

    if voice is None:

        await ctx.send(
            "❌ Бот не находится в голосовом канале."
        )

        return

    if not voice.is_playing() and not voice.is_paused():

        await ctx.send(
            "❌ Сейчас ничего не играет."
        )

        return

    await ctx.send(
        "⏭️ Пропускаю текущий трек..."
    )
    global vol_for_skip
    vol = vol_for_skip

    voice.stop()
    # print(show_queue)
    # play_next(guild_id, vol)

# =========================================================
# CLEAR QUEUE
# =========================================================

@bot.command()
async def clearqueue(ctx):

    player = get_player(
        ctx.guild.id
    )

    count = 0

    while not player.queue.empty():

        try:

            player.queue.get_nowait()

            count += 1

        except asyncio.QueueEmpty:

            break

    await ctx.send(
        f"🗑️ Очередь очищена.\n"
        f"Удалено треков: **{count}**"
    )


# =========================================================
# PAUSE
# =========================================================

@bot.command()
async def pause(ctx):

    voice = ctx.guild.voice_client

    if voice and voice.is_playing():

        voice.pause()

        await ctx.send(
            "⏸️ Музыка поставлена на паузу."
        )

    else:

        await ctx.send(
            "❌ Сейчас ничего не играет."
        )


# =========================================================
# RESUME
# =========================================================

@bot.command()
async def resume(ctx):

    voice = ctx.guild.voice_client

    if voice and voice.is_paused():

        voice.resume()

        await ctx.send(
            "▶️ Продолжаю воспроизведение."
        )

    else:

        await ctx.send(
            "❌ Музыка не находится на паузе."
        )


# =========================================================
# STOP
# =========================================================

@bot.command()
async def stop(ctx):

    player = get_player(
        ctx.guild.id
    )

    voice = ctx.guild.voice_client

    if voice is None:

        await ctx.send(
            "❌ Бот не находится в голосовом канале."
        )

        return

    # Очищаем очередь
    while not player.queue.empty():

        try:
            player.queue.get_nowait()

        except asyncio.QueueEmpty:
            break

    # Останавливаем текущий трек
    if voice.is_playing() or voice.is_paused():

        voice.stop()

        await ctx.send(
            "⏹️ Музыка остановлена.\n"
            "🗑️ Очередь очищена."
        )

    else:

        await ctx.send(
            "❌ Сейчас ничего не играет."
        )


# =========================================================
# LEAVE
# =========================================================

@bot.command()
async def leave(ctx):

    player = get_player(
        ctx.guild.id
    )

    voice = ctx.guild.voice_client

    if voice is None:

        await ctx.send(
            "❌ Бот не находится в голосовом канале."
        )

        return

    # Очищаем очередь
    while not player.queue.empty():

        try:
            player.queue.get_nowait()

        except asyncio.QueueEmpty:
            break

    # Останавливаем музыку
    if voice.is_playing() or voice.is_paused():

        voice.stop()

    await voice.disconnect()

    player.playing = False
    player.current = None

    await ctx.send(
        "👋 Вышел из голосового канала."
    )




# Ранг


@bot.command()
async def rank(ctx, *, user_name=''):
    try:
        if user_name=="":
            user_name = ctx.author.global_name
        if user_name[1] == '@':
            user_name = user_name[2:-1]
        print(user_name)
        if user_name not in [x.global_name for x in ctx.guild.members] and user_name not in [str(x.id) for x in ctx.guild.members] and user_name not in [x.nick for x in ctx.guild.members]:
            raise Exception("Данного пользователя нет на сервере")




        for memb in ctx.guild.members:
            print(memb.global_name)
            if memb.global_name == user_name or memb.nick == user_name or str(memb.id) == user_name:
                user_id = memb.id
                print(user_id, memb.id)
                member = await ctx.guild.fetch_member(user_id)
                print(member)
                break

        db = connect('db/exp.db')

        c = db.cursor()

        c.execute("SELECT CASE WHEN EXISTS (SELECT experience FROM experience WHERE user_id = ?) THEN (SELECT experience FROM experience WHERE user_id = ?) ELSE '0' END AS result", (user_id, user_id,))
        exp = c.fetchone()[0]

        msg = f"У пользователя {member.global_name} exp: {exp}"
        await ctx.send(msg)
    except Exception as e:
        await ctx.send(f'Ошибка: {e}')

@bot.command()
async def test(ctx, *, exp=123):


    add_exp(ctx.author.id,
            ctx.author.global_name,
            exp)

    await ctx.send('Опыт зачислен')

# SET AVATARKA
@bot.command()
async def set_logo(ctx):
    if not ctx.message.attachments:
        await ctx.send("Прикрепи изображение к команде!")
        return

    image = ctx.message.attachments[0]

    avatar_bytes = await image.read()

    try:
        await bot.user.edit(avatar=avatar_bytes)
        await ctx.send("Аватарка успешно изменена!")
    except Exception as e:
        await ctx.send(f"Ошибка: {e}")


@bot.event
async def on_command_error(ctx, error):
    await ctx.send(f"Ошибка: {error}")

@bot.event
async def on_message(message):

    if message.author.bot:
        return


    db = connect('db/exp.db')
    c = db.cursor()

    c.execute("""INSERT OR IGNORE INTO experience (user_id, user_name, experience)
        VALUES (?, ?, ?)""", (message.author.id, message.author.global_name, 0,))
    db.commit()
    db.close()

    #звание

    which_rank(message.author.id)



    if len(message.attachments) != 0 or message.content[0] != '!':
        db = connect('db/exp.db')
        c = db.cursor()


        c.execute("""
        UPDATE experience
        SET experience = experience + ?
        WHERE user_id = ?
        """, (9, message.author.id,))

        db.commit()
        db.close()

    await bot.process_commands(message)

@bot.command()
async def clear(ctx, amount: int):
    try:
        await ctx.channel.purge(limit=amount)
    except Exception as e:
        await ctx.send(f"Ошибка: {e}")

@bot.command()
async def top(ctx):
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

    c.execute("""
    SELECT * FROM EXPERIENCE ORDER BY experience
""")
    data = c.fetchall()
    print(data)
    answer = ''
    for x in data:
        answer = f"Пользователь {x[1]} имеет {x[2]} EXP; Ранг: {x[3]}" + "\n" + answer
    answer = f"Рейтинг Дискорд \n" + answer

    await ctx.send(answer)
    await ctx.send(answer_telegram)

@bot.event
async def on_voice_state_update(member, before, after):
    try:
        bot_voice_channel = member.guild.me.voice.channel
        if before.channel is not None and member.guild.me is not None and bot_voice_channel == before.channel:
            sigma = await bot.fetch_guild(before.channel.guild.id)
            vc = await bot.fetch_channel(before.channel.id)
            print(vc)
            if len(vc.members) == 1:
                await sigma.voice_client.disconnect()
                await member.send('Все вышли из ГС')
    except Exception as e:
        print(e)




async def get_posts(tag='zenless_zone_zero'):

    url = "https://api.rule34.xxx/index.php"
    print
    if tag != 'zenless_zone_zero':

        params = {
            "page": "dapi",
            "s": "post",
            "q": "index",
            "tags": tag,
            "limit": 10000,
            "pid": 1,
            "json": 1,
            "api_key": 'e7ac39308cce91c12e034952af1925480c646b11c757203931ce314dcbdeabf3e4e71a5eceaec3a745ffef3b1bb436623daf8b26dd943cbd13057003c050599f',
            "user_id": 6733123 }
    else:
    
        params = {
                "page": "dapi",
                "s": "post",
                "q": "index",
                "tags": tag,
                "limit": 1000,
                "pid": random.randint(1, 100),                    
                "json": 1,
                "api_key": 'e7ac39308cce91c12e034952af1925480c646b11c757203931ce314dcbdeabf3e4e71a5eceaec3a745ffef3b1bb436623daf8b26dd943cbd13057003c050599f',
                "user_id": 6733123 }

    async with aiohttp.ClientSession() as session:

        async with session.get(url, params=params) as response:

            response.raise_for_status()

            data = await response.json()

            return data

posts=[]
zzz_lock = asyncio.Lock()
@bot.command()
async def zzz(ctx, amount: int = 5, tag:str ='zenless_zone_zero'):
    try:
        if zzz_lock.locked():
            ctx.send('Уже выполняет команду')
            return
        async with zzz_lock:
            print(tag)
            posts = await get_posts(tag)

            print("Получено постов:", len(posts))
            print(posts)

            bad_tags = {"furry", "shemale", "futanari",'tentacles', 'loli', 'roblox'}

            for post in random.sample(posts, amount):
                tags = set(post["tags"].split())

                if not tags.intersection(bad_tags):
                    await ctx.send(post["file_url"])
    except Exception as e:
        await ctx.send(f"Ошибка {e}")



@bot.command()
async def zzz_video(ctx, tag='zenless_zone_zero'):
    if zzz_lock.locked():
        ctx.send('Уже выполняет команду')
        return


    async with zzz_lock:
        posts = await get_posts(tag)
        amount=300

        bad_tags = {"furry", "gay", "shemale", "futanari",'tentacles', 'loli'}

        for post in random.sample(posts, amount):
            tags = set(post["tags"].split())
            file_url = post["file_url"]
            print(file_url[-4:])
            if not tags.intersection(bad_tags) and file_url[-4:] == '.mp4':
                await ctx.send(post["file_url"])
bot.run(TOKEN)
