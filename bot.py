import os
import json
import logging
from anthropic import Anthropic
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = Anthropic()

# In-memory conversation history per user
conversation_history: dict[int, list] = {}

# Only allow this Telegram user ID (set via env var for security)
try:
    ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", "0"))
except (ValueError, TypeError):
    ALLOWED_USER_ID = 0


def is_allowed(user_id: int) -> bool:
    return ALLOWED_USER_ID == 0 or user_id == ALLOWED_USER_ID


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        return
    conversation_history[user_id] = []
    await update.message.reply_text(
        "Hey! Ich bin dein Claude-Assistent. Schreib mir einfach — ich merke mir das Gespräch.\n\n"
        "/reset — Gespräch zurücksetzen"
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        return
    conversation_history[user_id] = []
    await update.message.reply_text("Gespräch zurückgesetzt.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        await update.message.reply_text("Zugriff verweigert.")
        return

    user_text = update.message.text
    history = conversation_history.setdefault(user_id, [])

    # Add user message to history
    history.append({"role": "user", "content": user_text})

    # Keep last 20 messages to avoid token limits
    if len(history) > 20:
        history = history[-20:]
        conversation_history[user_id] = history

    await update.message.chat.send_action("typing")

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            system=(
                "Du bist ein hilfreicher persönlicher Assistent. "
                "Antworte präzise und auf Deutsch, außer der Nutzer schreibt in einer anderen Sprache."
            ),
            messages=history,
        )

        assistant_text = response.content[0].text
        history.append({"role": "assistant", "content": assistant_text})

        await update.message.reply_text(assistant_text)

    except Exception as e:
        logger.error(f"Claude API error: {e}")
        await update.message.reply_text("Fehler bei der Verbindung zur KI. Bitte versuche es nochmal.")


def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    port = int(os.environ.get("PORT", "8080"))
    webhook_url = os.environ.get("WEBHOOK_URL")

    if webhook_url:
        # Production: webhook mode
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            webhook_url=f"{webhook_url}/webhook",
            url_path="/webhook",
        )
    else:
        # Local development: polling mode
        logger.info("Running in polling mode (local dev)")
        app.run_polling()


if __name__ == "__main__":
    main()
