import os
import asyncio
import httpx
import json
import re
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

async def send_daily_content():
    bot = Bot(token=TELEGRAM_TOKEN)
    topic = TOPICS[datetime.now().timetuple().tm_yday % len(TOPICS)]
    print(f"[{datetime.now()}] موضوع: {topic}")
    try:
        raw_news = await fetch_tax_news()
        content = await generate_tax_content(topic, raw_news)
        await bot.send_message(chat_id=CHANNEL_ID, text=format_message(content), parse_mode=ParseMode.MARKDOWN)
        print(f"✅ ارسال موفق")
    except Exception as e:
        print(f"❌ خطا: {e}")

async def main():
    scheduler = AsyncIOScheduler(timezone="Asia/Tehran")
    scheduler.add_job(send_daily_content, "cron", hour=8, minute=30)
    scheduler.start()
    print("✅ ربات رادین فعال — ساعت ۸:۳۰ صبح")
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
