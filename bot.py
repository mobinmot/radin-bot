import os
import asyncio
import httpx
import json
import re
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
ADMIN_CHAT_ID = 5870651461

TOPICS = [
    "مالیات بر ارزش افزوده",
    "مالیات بر درآمد و عملکرد",
    "تجارت الکترونیک و مالیات",
    "جرائم و معافیت‌های مالیاتی",
    "مهلت‌های مالیاتی",
    "بخشنامه‌های جدید سازمان امور مالیاتی",
    "حسابداری مالیاتی",
]

pending_posts = {}

async def fetch_tax_news() -> str:
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get("https://www.tax.gov.ir/portal/home/?59506/", headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                clean = re.sub(r'<[^>]+>', ' ', resp.text)
                clean = re.sub(r'\s+', ' ', clean).strip()
                return clean[:3000]
    except Exception as e:
        print(f"خطا: {e}")
    return ""

async def generate_tax_content(topic: str, raw_news: str) -> dict:
    today = datetime.now().strftime("%Y/%m/%d")
    ctx = f"اطلاعات از سازمان امور مالیاتی:\n{raw_news[:1500]}\n\nبا استفاده از این اطلاعات،" if raw_news else "بر اساس قوانین مالیاتی ایران،"
    prompt = f"""امروز {today} است. {ctx} درباره «{topic}» پست تلگرامی فارسی بنویس.
فقط JSON خالص:
{{"title":"عنوان با ایموجی","body":"متن ۸۰ تا ۱۰۰ کلمه","tip":"نکته کلیدی","hashtags":"#مالیات #رادین #حسابداری"}}"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0.7,"maxOutputTokens":1000}})
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        return json.loads(text.replace("```json","").replace("```","").strip())

def format_message(content: dict) -> str:
    return f"{content['title']}\n\n{content['body']}\n\n💡 *نکته کلیدی:*\n{content['tip']}\n\n━━━━━━━━━━━━━━━\n📎 منبع: سازمان امور مالیاتی ایران\n{content['hashtags']}\n📌 کانال رادین | مشاوره مالیاتی"

async def send_preview(bot: Bot):
    topic = TOPICS[datetime.now().timetuple().tm_yday % len(TOPICS)]
    try:
        raw_news = await fetch_tax_news()
        content = await generate_tax_content(topic, raw_news)
        message = format_message(content)
        post_id = str(datetime.now().timestamp())
        pending_posts[post_id] = message
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ تایید و انتشار", callback_data=f"approve_{post_id}"),
                InlineKeyboardButton("🔄 تولید مجدد", callback_data=f"regenerate_{post_id}"),
            ],
            [InlineKeyboardButton("❌ رد کردن", callback_data=f"reject_{post_id}")]
        ])
        await bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"📋 *پیش‌نویس پست امروز:*\n\n{message}", parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        print(f"✅ پیش‌نویس ارسال شد")
    except Exception as e:
        print(f"❌ خطا: {e}")
        await bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"❌ خطا در تولید محتوا: {e}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("approve_"):
        post_id = data.replace("approve_", "")
        message = pending_posts.get(post_id)
        if message:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=message, parse_mode=ParseMode.MARKDOWN)
            await query.edit_message_text("✅ پست در کانال منتشر شد!")
            del pending_posts[post_id]
    elif data.startswith("reject_"):
        post_id = data.replace("reject_", "")
        if post_id in pending_posts:
            del pending_posts[post_id]
        await query.edit_message_text("❌ پست رد شد.")
    elif data.startswith("regenerate_"):
        await query.edit_message_text("🔄 در حال تولید پست جدید...")
        topic = TOPICS[datetime.now().timetuple().tm_yday % len(TOPICS)]
        try:
            raw_news = await fetch_tax_news()
            content = await generate_tax_content(topic, raw_news)
            message = format_message(content)
            post_id = str(datetime.now().timestamp())
            pending_posts[post_id] = message
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ تایید و انتشار", callback_data=f"approve_{post_id}"),
                    InlineKeyboardButton("🔄 تولید مجدد", callback_data=f"regenerate_{post_id}"),
                ],
                [InlineKeyboardButton("❌ رد کردن", callback_data=f"reject_{post_id}")]
            ])
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"📋 *پیش‌نویس جدید:*\n\n{message}", parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        except Exception as e:
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"❌ خطا: {e}")

async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CallbackQueryHandler(button_handler))
    scheduler = AsyncIOScheduler(timezone="Asia/Tehran")
    scheduler.add_job(send_preview, "cron", hour=8, minute=0, args=[app.bot])
    scheduler.start()
    print("✅ ربات رادین فعال شد")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    # پیام تست موقع شروع
    await send_preview(app.bot)
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        await app.updater.stop()
        await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
