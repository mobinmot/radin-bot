import os
import asyncio
import httpx
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
from telegram.constants import ParseMode

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

TOPICS = [
    "مالیات بر ارزش افزوده",
    "مالیات بر درآمد و عملکرد",
    "تجارت الکترونیک و مالیات",
    "جرائم و معافیت‌های مالیاتی",
    "مهلت‌های مالیاتی",
    "بخشنامه‌های جدید سازمان امور مالیاتی",
    "حسابداری مالیاتی",
]

async def generate_tax_content(topic):
    today = datetime.now().strftime("%Y/%m/%d")
    prompt = f"""امروز {today} است. درباره موضوع مالیاتی «{topic}» در ایران یک پست تلگرامی به فارسی بنویس.
فرمت دقیق JSON بدون توضیح اضافی:
{{"title":"عنوان با ایموجی","body":"متن ۸۰ تا ۱۰۰ کلمه","tip":"نکته کلیدی","hashtags":"#مالیات #رادین"}}
فقط JSON خالص برگردان."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0.7,"maxOutputTokens":1000}})
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        text = text.replace("```json","").replace("```","").strip()
        import json
        return json.loads(text)

def format_message(content):
    return f"""{content['title']}\n\n{content['body']}\n\n💡 *نکته کلیدی:*\n{content['tip']}\n\n━━━━━━━━━━━━━━━\n{content['hashtags']}\n📌 کانال رادین | مشاوره مالیاتی"""

async def send_daily_content():
    bot = Bot(token=TELEGRAM_TOKEN)
    day = datetime.now().timetuple().tm_yday
    topic = TOPICS[day % len(TOPICS)]
    print(f"[{datetime.now()}] ارسال: {topic}")
    try:
        content = await generate_tax_content(topic)
        await bot.send_message(chat_id=CHANNEL_ID, text=format_message(content), parse_mode=ParseMode.MARKDOWN)
        print(f"[{datetime.now()}] ✅ موفق")
    except Exception as e:
        print(f"[{datetime.now()}] ❌ خطا: {e}")

async def main():
    scheduler = AsyncIOScheduler(timezone="Asia/Tehran")
    scheduler.add_job(send_daily_content, "cron", hour=8, minute=30)
    scheduler.start()
    print("✅ ربات رادین شروع شد")
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
