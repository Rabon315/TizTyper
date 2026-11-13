"""بات تیزتایپر: /s [تعداد دور]"""
import asyncio
import html
import logging
import os
import random
import re
import time
from collections import deque

ROUNDS_DEFAULT, MAX_ROUNDS, ROUND_SECONDS = 10, 30, 30
MEDALS = ["🥇", "🥈", "🥉"]

SENTENCES = [
    "ممه و کون و کیر، شروع مسابقه", "کیرم تو این کیبورد خراب",
    "کص ننه ایلیا بیگواد", "این کصخل هنوز داره تایپ می‌کنه",
    "چه کصری گفتی، دوباره بنویس", "کیر خر هم از این سریع‌تر تایپ می‌کنه",
    "ممه گنده و کون گرد", "کونت رو جمع کن، مسابقه شروع شد",
    "کیر تو شانس من که باز اشتباه زدم", "این چه کصشر عجیبی بود",
    "کصخل بازی درنیار و درست تایپ کن", "تخمم هم نیست کی اول می‌شه",
    "کون لق این اینترنت داغون", "کیرم تو رکورد قبلی، رکورد تازه می‌زنم",
    "ممه کیر کون کص، چهار کلمه‌ی طلایی", "جنده‌ی کیبوردباز رکورد رو شکست",
    "کون‌گشادها از مسابقه جا می‌مونن", "کیر خر رو با سرعت تایپ اشتباه نگیر",
    "کص نگو، متن رو دقیق بنویس", "این مسابقه پر از کصخل‌های سریعه",
    "کون لق هرکی وسط بازی اسپم کنه", "کیر تو این شانس عجیب و غریب",
    "ممه و کیر و کون و کلی دردسر", "کصشر ننویس، همون متن رو بزن",
    "کون‌گردی تعطیل، وقت مسابقه‌ست", "کیرم تو این دور سخت",
    "کصخل جان، فاصله‌ها مهم نیست", "این یکی رو مثل آدم تایپ کن",
    "کون لق تایپ اشتباه و اینترنت ضعیف", "لعنت به این رکورد لعنتی",
]

WORD_BANK = """
ممه کیر کون کص کس تخم جنده کصخل کونی کیری کونده سکسی شهوتی
لخت عوضی آشغال بی‌شعور احمق خل چل دیوث پفیوز بیشعور کثافت
نکبت گوه گه شاش ریدم ریدن لاشی بی‌ناموس پدرسگ مادرجنده جاکش
کثیف داغون خفن خنگ تنبل بی‌اعصاب خرابکار چرت پرت مسخره افتضاح
گنده گرد تپل چاق دراز کوتاه تند سریع کند کیبورد تایپ رکورد مسابقه
برنده بازنده اینترنت اعصاب
""".split()

TEMPLATES = [
    "{a} {b} {c}", "{a} تو {b}", "{a} و {b} و {c}",
    "{b} {a} {c}", "{a} گنده و {b} گرد",
    "این {a} {b} هنوز {c}", "{a} لعنتی، {b} رو جمع کن",
    "کیرم تو {a} و {b}", "کون لق {a}، {b} شروع شد",
    "{a} نگو، {b} رو تایپ کن",
]

_ASCII = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_JUNK = re.compile(r"[\s\u200c\u200e\u200f.,،؛:!?؟\"'«»()\-_…]+")


def norm(text):
    return _JUNK.sub("", (text or "").replace("ي", "ی").replace("ك", "ک").translate(_ASCII).lower())


def gen_phrase(recent):
    used = {norm(x) for x in recent}
    candidates = [s for s in SENTENCES if norm(s) not in used]
    for _ in range(500):
        a, b, c = random.sample(WORD_BANK, 3)
        phrase = random.choice(TEMPLATES).format(a=a, b=b, c=c)
        if norm(phrase) not in used:
            candidates.append(phrase)
            break
    if not candidates:
        for _ in range(1500):
            phrase = " ".join(random.sample(WORD_BANK, random.choice([3, 4, 5])))
            if norm(phrase) not in used:
                candidates.append(phrase)
                break
    if not candidates:
        recent.clear()
        return gen_phrase(recent)
    phrase = random.choice(candidates)
    recent.append(phrase)
    return phrase


# جلوگیری از تکرار عبارت در هر گروه؛ حافظه تا زمان روشن بودن فرایند باقی می‌ماند.
GAMES, RECENT = {}, {}


class Game:
    def __init__(self, chat_id, rounds, starter, send):
        self.chat_id, self.rounds, self.starter, self.send = chat_id, rounds, starter, send
        self.recent = RECENT.setdefault(chat_id, deque(maxlen=500))
        self.phrase = None
        self.t0 = 0.0
        self.winner = None
        self.ev = asyncio.Event()
        self.stopped = False
        self.wins, self.times, self.names = {}, {}, {}

    async def run(self):
        try:
            await self.send(f"⌨️ <b>تیزتایپر</b> — {self.rounds} دور!\nهرکی زودتر متن رو دقیق بنویسه، برنده‌ست. آماده باشید...")
            await asyncio.sleep(2)
            for i in range(1, self.rounds + 1):
                if self.stopped:
                    break
                await self._round(i)
                await asyncio.sleep(1.5)
            await self._finish()
        finally:
            GAMES.pop(self.chat_id, None)

    async def _round(self, i):
        self.winner = None
        self.ev.clear()
        await self.send(f"🔔 دور <b>{i}/{self.rounds}</b> — آماده...")
        await asyncio.sleep(random.uniform(1.5, 3.5))
        self.phrase = gen_phrase(self.recent)
        await self.send(f"✍️ بنویس:\n\n<b>« {html.escape(self.phrase)} »</b>")
        self.t0 = time.monotonic()
        try:
            await asyncio.wait_for(self.ev.wait(), ROUND_SECONDS)
        except asyncio.TimeoutError:
            pass
        self.phrase = None
        if self.winner:
            _, name, secs = self.winner
            await self.send(f"🏆 <b>{html.escape(name)}</b> برنده شد! ⏱ {secs:.2f} ثانیه")
        elif not self.stopped:
            await self.send("⏰ کسی ننوشـت؛ دور بعد!")

    def on_text(self, user_id, name, text):
        if self.phrase and not self.winner and norm(text) == norm(self.phrase):
            secs = time.monotonic() - self.t0
            self.winner = (user_id, name, secs)
            self.names[user_id] = name
            self.wins[user_id] = self.wins.get(user_id, 0) + 1
            self.times[user_id] = self.times.get(user_id, 0.0) + secs
            self.ev.set()

    async def _finish(self):
        if not self.wins:
            await self.send("🤷 کسی امتیازی نگرفت!")
            return
        rows = sorted(self.wins, key=lambda uid: (-self.wins[uid], self.times[uid]))
        lines = [
            f"{MEDALS[i] if i < 3 else '▫️'} <b>{html.escape(self.names[uid])}</b> — "
            f"{self.wins[uid]} برد · میانگین {self.times[uid] / self.wins[uid]:.2f}s"
            for i, uid in enumerate(rows[:10])
        ]
        await self.send("🏁 <b>پایان!</b>\n\n" + "\n".join(lines) +
                        f"\n\n👑 قهرمان: <b>{html.escape(self.names[rows[0]])}</b>")


def main():
    from aiogram import Bot, Dispatcher, F
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from aiogram.filters import Command, CommandObject
    from aiogram.types import Message
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("متغیر محیطی BOT_TOKEN تنظیم نشده است.")
    bot = Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    async def private_only_message(m: Message):
        await m.answer(
            "بازی فقط داخل گروه قابل اجراست. ربات رو به گروهت اضافه کن و اونجا /s رو بزن."
        )

    @dp.message(Command("start"))
    async def welcome(m: Message):
        if m.chat.type != "private":
            return
        me = await bot.get_me()
        add_url = f"https://t.me/{me.username}?startgroup=true"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="افزودن بازی به گروه", url=add_url)
        ]])
        await m.answer(
            "سلام! به تیزتایپر خوش اومدی.\n"
            "این بازی فقط داخل گروه اجرا می‌شه. ربات رو به گروهت اضافه کن "
            "و برای شروع بازی، دستور /s رو بزن.",
            reply_markup=keyboard
        )

    @dp.message(Command("s"))
    async def start(m: Message, command: CommandObject):
        if m.chat.type == "private":
            return await private_only_message(m)
        if m.chat.id in GAMES:
            return await m.answer("یه بازی در جریانه ⌨️ (برای توقف: /stop)")
        n = ROUNDS_DEFAULT
        if command.args and command.args.strip().isdigit():
            n = max(1, min(MAX_ROUNDS, int(command.args.strip())))
        async def send(text, cid=m.chat.id):
            await bot.send_message(cid, text)
        g = GAMES[m.chat.id] = Game(m.chat.id, n, m.from_user.id, send)
        g.task = asyncio.create_task(g.run())

    @dp.message(Command("stop"))
    async def stop(m: Message):
        if m.chat.type == "private":
            return await private_only_message(m)
        g = GAMES.get(m.chat.id)
        if not g:
            return
        member = await bot.get_chat_member(m.chat.id, m.from_user.id)
        if m.from_user.id == g.starter or member.status in ("administrator", "creator"):
            g.stopped = True
            g.ev.set()
            await m.answer("بازی متوقف شد.")

    @dp.message(F.text & ~F.text.startswith("/"))
    async def text_handler(m: Message):
        g = GAMES.get(m.chat.id)
        if g and m.from_user and not m.from_user.is_bot:
            g.on_text(m.from_user.id, m.from_user.full_name, m.text)

    async def run():
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)

    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())


if __name__ == "__main__":
    main()
