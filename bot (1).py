import os
import re
import hmac
import hashlib
import time
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

# ── Config (loaded from environment variables) ──────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
SHOPEE_APP_ID   = os.environ["SHOPEE_APP_ID"]
SHOPEE_SECRET   = os.environ["SHOPEE_SECRET"]

# ── Shopee Affiliate API ─────────────────────────────────────────────────────
SHOPEE_API_URL = "https://open-api.affiliate.shopee.sg/graphql"

def generate_auth_header(app_id: str, secret: str) -> dict:
    timestamp = str(int(time.time()))
    payload = f"{app_id}{timestamp}"
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "Authorization": f"SHA256 Credential={app_id},Timestamp={timestamp},Signature={signature}"
    }

def convert_to_affiliate_link(original_url: str) -> str | None:
    headers = generate_auth_header(SHOPEE_APP_ID, SHOPEE_SECRET)
    query = """
    mutation generateShortLink($input: GenerateShortLinkInput!) {
        generateShortLink(input: $input) {
            shortLink
            longLink
        }
    }
    """
    variables = {
        "input": {
            "originUrl": original_url,
            "subId": "tgbot"
        }
    }
    try:
        print(f"[DEBUG] Converting URL: {original_url}")
        response = requests.post(
            SHOPEE_API_URL,
            json={"query": query, "variables": variables},
            headers=headers,
            timeout=10
        )
        print(f"[DEBUG] API status code: {response.status_code}")
        print(f"[DEBUG] API response: {response.text}")
        data = response.json()
        return data["data"]["generateShortLink"]["shortLink"]
    except Exception as e:
        print(f"[ERROR] Failed to convert link: {e}")
        return None

# ── Link Detection ───────────────────────────────────────────────────────────
# Matches: shopee.sg, s.shopee.sg, shp.ee, sg.shp.ee, etc.
SHOPEE_PATTERN = re.compile(
    r"https?://(?:\w+\.)*(?:shopee\.sg|shp\.ee)[^\s]*",
    re.IGNORECASE
)

def find_shopee_links(text: str) -> list[str]:
    return SHOPEE_PATTERN.findall(text)

# ── Telegram Handlers ────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hi! Send me any Shopee Singapore link and I'll convert it into an affiliate link for you!"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return

    print(f"[DEBUG] Received message: {message.text}")
    links = find_shopee_links(message.text)
    print(f"[DEBUG] Found links: {links}")
    if not links:
        return

    reply_lines = []
    for link in links:
        affiliate_link = convert_to_affiliate_link(link)
        if affiliate_link:
            reply_lines.append(f"🛍️ Affiliate link:\n{affiliate_link}")
        else:
            reply_lines.append(f"⚠️ Could not convert: {link}")

    if reply_lines:
        await message.reply_text("\n\n".join(reply_lines))

# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ Bot is running...")
    app.run_polling()
