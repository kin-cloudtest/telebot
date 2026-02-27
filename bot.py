import os
import re
import hashlib
import time
import json
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

# ── Config ───────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN  = os.environ["TELEGRAM_TOKEN"]
SHOPEE_APP_ID   = os.environ["SHOPEE_APP_ID"]
SHOPEE_SECRET   = os.environ["SHOPEE_SECRET"]
SUPABASE_URL    = os.environ["SUPABASE_URL"]
SUPABASE_KEY    = os.environ["SUPABASE_KEY"]

SHOPEE_API_URL  = "https://open-api.affiliate.shopee.sg/graphql"

# ── Supabase Helpers ─────────────────────────────────────────────────────────
def supabase_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }

def is_returning_user(user_id: int) -> bool:
    """Check if user already exists in the database."""
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/users?user_id=eq.{user_id}&select=user_id",
        headers=supabase_headers(),
        timeout=10
    )
    return len(res.json()) > 0

def save_user(user_id: int, first_name: str):
    """Insert new user into the database."""
    requests.post(
        f"{SUPABASE_URL}/rest/v1/users",
        headers={**supabase_headers(), "Prefer": "ignore-duplicates"},
        json={"user_id": user_id, "first_name": first_name},
        timeout=10
    )

# ── Shopee Affiliate API ─────────────────────────────────────────────────────
def generate_auth_header(app_id: str, secret: str, payload: str) -> dict:
    timestamp = str(int(time.time()))
    raw = f"{app_id}{timestamp}{payload}{secret}"
    signature = hashlib.sha256(raw.encode()).hexdigest()
    return {
        "Content-Type": "application/json",
        "Authorization": f"SHA256 Credential={app_id},Timestamp={timestamp},Signature={signature}"
    }

def convert_to_affiliate_link(original_url: str) -> str | None:
    query = f"""
    mutation {{
        generateShortLink(
            input: {{
                originUrl: "{original_url}"
                subIds: ["tgbot"]
            }}
        ) {{
            shortLink
        }}
    }}
    """
    body = json.dumps({"query": query}, separators=(',', ':'))
    try:
        headers = generate_auth_header(SHOPEE_APP_ID, SHOPEE_SECRET, body)
        response = requests.post(SHOPEE_API_URL, data=body, headers=headers, timeout=15)
        data = response.json()
        return data["data"]["generateShortLink"]["shortLink"]
    except KeyError:
        return None
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")
        return None

# ── Link Detection ───────────────────────────────────────────────────────────
SHOPEE_PATTERN = re.compile(
    r"https?://(?:\w+\.)*(?:shopee\.sg|shp\.ee)[^\s]*",
    re.IGNORECASE
)

def find_shopee_links(text: str) -> list[str]:
    return SHOPEE_PATTERN.findall(text)

# ── Telegram Handlers ────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    first_name = user.first_name or "there"

    if is_returning_user(user_id):
        await update.message.reply_text(
            f"👋 Welcome back, {first_name}! Great to see you again.\n\n"
            "Send me your Shopee links and I'll convert them for you 🛍️"
        )
    else:
        save_user(user_id, first_name)
        await update.message.reply_text(
            f"👋 Welcome to Kinbot, I am your friendly asst here to save you $$$\n\n"
            "Please input your links in the following format (up to 5):\n\n"
            "https://s.shopee.sg/xxxxx\n"
            "https://s.shopee.sg/xxxxx\n"
            "https://s.shopee.sg/xxxxx"
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return

    links = find_shopee_links(message.text)
    if not links:
        return

    if len(links) > 5:
        await message.reply_text("⚠️ Please send up to 5 links at a time!")
        return

    reply_lines = []
    for link in links:
        affiliate_link = convert_to_affiliate_link(link)
        if affiliate_link:
            reply_lines.append(f"🛍️ {affiliate_link}")
        else:
            reply_lines.append(f"⚠️ Could not convert: {link}")

    if reply_lines:
        await message.reply_text("Happy shopping! 🛍️\n\n" + "\n\n".join(reply_lines))

# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ Bot is running...")
    app.run_polling()
