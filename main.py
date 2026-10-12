import asyncio
import json
import os
import random
import logging
import time
from collections import deque

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from telethon import Button, TelegramClient, events
from telethon.sessions import StringSession

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
TELEGRAM_SESSION = os.environ.get("TELEGRAM_SESSION", "")
ADMIN_PASSWORD = "/admin14758"
COMMENTS_FILE = "comments.json"
SETTINGS_FILE = "settings.json"
MIN_COMMENT_DELAY_SECONDS = 5
MAX_COOLDOWN_MINUTES = 10080  # Seven days

DEFAULT_COMMENTS = [
    "I copy traded one wallet today and walked away with over $15.6k",
    "This signal just made me $8,400 in under 2 hours, unbelievable",
    "Been following this channel for weeks, finally pulled the trigger and made $12k",
    "Just closed a trade for +$6,200 profit thanks to this call",
    "I turned $500 into $4,800 following this channel's tips",
    "Made my weekly salary in one trade today, this channel is gold",
    "Copy traded this and banked $9,100 — my best trade ever",
    "Went in with $1k and came out with $7.3k, these calls are insane",
    "Finally a channel that actually delivers, up $11k this week alone",
    "This trade just paid my rent for 3 months, thank you!",
]

bot_running = True
authenticated_users = set()


def load_settings():
    defaults = {"cooldown_minutes": 0, "last_comment_at": {}}
    try:
        with open(SETTINGS_FILE, "r") as f:
            data = json.load(f)
        cooldown = int(data.get("cooldown_minutes", 0))
        if cooldown < 0 or cooldown > MAX_COOLDOWN_MINUTES:
            cooldown = 0
        last_comment_at = {
            str(chat_id): float(timestamp)
            for chat_id, timestamp in data.get("last_comment_at", {}).items()
        }
        return {"cooldown_minutes": cooldown, "last_comment_at": last_comment_at}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return defaults


settings = load_settings()
cooldown_minutes = settings["cooldown_minutes"]
last_comment_at = settings["last_comment_at"]


def save_settings():
    with open(SETTINGS_FILE, "w") as f:
        json.dump(
            {
                "cooldown_minutes": cooldown_minutes,
                "last_comment_at": last_comment_at,
            },
            f,
            indent=2,
        )


def post_arrived_after_cooldown(received_at, last_comment, minutes):
    return received_at >= last_comment + minutes * 60


def load_comments():
    if os.path.exists(COMMENTS_FILE):
        try:
            with open(COMMENTS_FILE, "r") as f:
                data = json.load(f)
                return data.get("comments", DEFAULT_COMMENTS)
        except Exception:
            pass
    save_comments(DEFAULT_COMMENTS)
    return list(DEFAULT_COMMENTS)


def save_comments(comments):
    with open(COMMENTS_FILE, "w") as f:
        json.dump({"comments": comments}, f, indent=2)


BUTTON_STATUS = "📊 Status"
BUTTON_LIST_COMMENTS = "🗒️ List comments"
BUTTON_ADD_COMMENT = "➕ Add comment"
BUTTON_DELETE_COMMENT = "🗑️ Delete comment"
BUTTON_SET_COOLDOWN = "⏱️ Set cooldown"
BUTTON_START_BOT = "▶️ Start bot"
BUTTON_STOP_BOT = "⏹️ Stop bot"
BUTTON_UNLOCK = "🔐 Unlock controls"
BUTTON_CANCEL = "❌ Cancel"


def controls_keyboard():
    return [
        [Button.text(BUTTON_STATUS), Button.text(BUTTON_LIST_COMMENTS)],
        [Button.text(BUTTON_ADD_COMMENT), Button.text(BUTTON_DELETE_COMMENT)],
        [
            Button.text(BUTTON_SET_COOLDOWN),
            Button.text(BUTTON_START_BOT),
            Button.text(BUTTON_STOP_BOT),
        ],
    ]


def unlock_keyboard():
    return [[Button.text(BUTTON_UNLOCK)]]


def cancel_keyboard():
    return [[Button.text(BUTTON_CANCEL)]]


async def run():
    global bot_running, cooldown_minutes

    if not API_ID or not API_HASH:
        logger.error("API_ID and API_HASH are required. Set them as Replit Secrets.")
        return

    if not TELEGRAM_SESSION:
        logger.error("TELEGRAM_SESSION is not set. Run login.py first to generate a session string.")
        return

    user_client = TelegramClient(StringSession(TELEGRAM_SESSION), API_ID, API_HASH)
    await user_client.connect()
    if not await user_client.is_user_authorized():
        logger.error("UserBot session is not authorized. Run login.py to generate a fresh TELEGRAM_SESSION.")
        await user_client.disconnect()
        return
    logger.info("UserBot connected successfully.")

    bot_client = None
    if BOT_TOKEN:
        bot_client = TelegramClient(StringSession(), API_ID, API_HASH)
        await bot_client.start(bot_token=BOT_TOKEN)
        logger.info("Control Bot connected successfully.")
    else:
        logger.warning("BOT_TOKEN not set — control bot disabled.")

    pending_posts = {}
    sending_channels = set()
    seen_posts = set()
    seen_post_order = deque()

    async def comment_on_pending_post(channel_id):
        channel_key = str(channel_id)
        try:
            await asyncio.sleep(MIN_COMMENT_DELAY_SECONDS)
            if not bot_running:
                return

            chat = await user_client.get_entity(channel_id)
            chat_title = getattr(chat, "title", str(channel_id))
            if not bot_running:
                return

            pending = pending_posts.get(channel_id)
            if pending is None:
                return
            message_id, received_at = pending
            if not post_arrived_after_cooldown(
                received_at, last_comment_at.get(channel_key, 0), cooldown_minutes
            ):
                logger.info(
                    "Ignoring an old post in [%s]; it arrived during the cooldown.",
                    chat_title,
                )
                return

            comments = load_comments()
            if not comments:
                logger.warning("No comments available to post.")
                return

            chosen = random.choice(comments)
            sending_channels.add(channel_id)
            try:
                try:
                    await user_client.send_message(
                        entity=channel_id,
                        message=chosen,
                        comment_to=message_id,
                    )
                    logger.info(
                        f"Commented on post in [{chat_title}]: {chosen[:60]}..."
                    )
                except Exception:
                    try:
                        await user_client.send_message(
                            entity=channel_id,
                            message=chosen,
                            reply_to=message_id,
                        )
                        logger.info(
                            f"Replied to post in [{chat_title}]: {chosen[:60]}..."
                        )
                    except Exception as error:
                        logger.error(
                            f"Could not comment in [{chat_title}]: {error}"
                        )
                        return

                last_comment_at[channel_key] = time.time()
                save_settings()
            finally:
                sending_channels.discard(channel_id)
        except Exception:
            logger.exception("Failed while processing a new post in [%s].", channel_id)
        finally:
            pending_posts.pop(channel_id, None)

    @user_client.on(events.NewMessage(incoming=True))
    async def handle_channel_post(event):
        if not bot_running:
            return
        message = event.message
        if not message or not message.text:
            return
        if not getattr(message, "post", False):
            return

        post_key = (event.chat_id, message.id)
        if post_key in seen_posts:
            return
        seen_posts.add(post_key)
        seen_post_order.append(post_key)
        if len(seen_post_order) > 5000:
            seen_posts.discard(seen_post_order.popleft())

        channel_id = event.chat_id
        channel_key = str(channel_id)
        received_at = time.time()
        if not post_arrived_after_cooldown(
            received_at, last_comment_at.get(channel_key, 0), cooldown_minutes
        ):
            logger.info(
                "Ignoring post in [%s]; its %s-minute cooldown is still active.",
                channel_id,
                cooldown_minutes,
            )
            return

        if channel_id in sending_channels:
            logger.info(
                "Ignoring post in [%s]; a comment is already being sent.", channel_id
            )
            return

        if channel_id in pending_posts:
            pending_posts[channel_id] = (message.id, received_at)
            logger.info("Selected the latest eligible post in [%s].", channel_id)
            return

        pending_posts[channel_id] = (message.id, received_at)
        asyncio.create_task(comment_on_pending_post(channel_id))

    if bot_client:
        pending_actions = {}

        async def show_controls(event, text):
            await event.respond(text, buttons=controls_keyboard())

        async def handle_control_message(event):
            global bot_running, cooldown_minutes

            if not event.is_private:
                return
            text = (event.raw_text or "").strip()
            if not text:
                return

            sender_id = event.sender_id
            pending = pending_actions.get(sender_id)

            if text == BUTTON_CANCEL:
                pending_actions.pop(sender_id, None)
                await show_controls(event, "Cancelled.")
                return

            if text == "/start":
                if sender_id in authenticated_users:
                    await show_controls(event, "Telegram AutoComment controls:")
                else:
                    await event.respond(
                        "Press Unlock controls, then enter your admin password.",
                        buttons=unlock_keyboard(),
                    )
                return

            if text == BUTTON_UNLOCK and sender_id not in authenticated_users:
                pending_actions[sender_id] = "authenticate"
                await event.respond(
                    "Enter the admin password, or press Cancel.",
                    buttons=cancel_keyboard(),
                )
                return

            if text == ADMIN_PASSWORD and pending != "authenticate":
                authenticated_users.add(sender_id)
                pending_actions.pop(sender_id, None)
                await show_controls(event, "Authenticated. Choose an action below.")
                return

            if pending == "authenticate":
                if text in {ADMIN_PASSWORD, ADMIN_PASSWORD.lstrip("/")}:
                    authenticated_users.add(sender_id)
                    pending_actions.pop(sender_id, None)
                    await show_controls(event, "Authenticated. Choose an action below.")
                else:
                    await event.respond(
                        "That password is incorrect. Try again or press Cancel.",
                        buttons=cancel_keyboard(),
                    )
                return

            if sender_id not in authenticated_users:
                await event.respond(
                    "Unlock controls first using the button below.",
                    buttons=unlock_keyboard(),
                )
                return

            if pending == "add_comment":
                comments = load_comments()
                comments.append(text)
                save_comments(comments)
                pending_actions.pop(sender_id, None)
                await show_controls(event, f"Comment added. Total: {len(comments)}")
                return

            if pending == "delete_comment":
                if not text.isdigit():
                    await event.respond(
                        "Send the comment number to delete, or press Cancel.",
                        buttons=cancel_keyboard(),
                    )
                    return
                idx = int(text) - 1
                comments = load_comments()
                if idx < 0 or idx >= len(comments):
                    await event.respond(
                        f"Invalid number. Choose 1 to {len(comments)}, or press Cancel.",
                        buttons=cancel_keyboard(),
                    )
                    return
                removed = comments.pop(idx)
                save_comments(comments)
                pending_actions.pop(sender_id, None)
                await show_controls(event, f"Removed comment: {removed}")
                return

            if pending == "set_cooldown":
                if not text.isdigit():
                    await event.respond(
                        "Send a whole number of minutes from 0 to "
                        f"{MAX_COOLDOWN_MINUTES}, or press Cancel.",
                        buttons=cancel_keyboard(),
                    )
                    return
                minutes = int(text)
                if minutes > MAX_COOLDOWN_MINUTES:
                    await event.respond(
                        f"Maximum is {MAX_COOLDOWN_MINUTES} minutes. Try again or press Cancel.",
                        buttons=cancel_keyboard(),
                    )
                    return
                cooldown_minutes = minutes
                save_settings()
                pending_actions.pop(sender_id, None)
                await show_controls(
                    event,
                    "Per-channel cooldown set to "
                    f"{minutes} minute(s). 0 disables the extra cooldown.",
                )
                return

            if text in {BUTTON_STATUS, "/status"}:
                await show_controls(
                    event,
                    f"Auto-commenting: {'ON' if bot_running else 'OFF'}\n"
                    f"Comments in pool: {len(load_comments())}\n"
                    f"Per-channel cooldown: {cooldown_minutes} minute(s)\n"
                    "Posts received during cooldown are ignored.",
                )
                return

            if text in {BUTTON_LIST_COMMENTS, "/listcomments"}:
                comments = load_comments()
                if not comments:
                    await show_controls(event, "No comments saved yet.")
                    return
                lines = "\n".join(f"{i + 1}. {comment}" for i, comment in enumerate(comments))
                await show_controls(event, f"Saved comments:\n\n{lines[:3800]}")
                return

            if text == BUTTON_ADD_COMMENT:
                pending_actions[sender_id] = "add_comment"
                await event.respond(
                    "Send the comment text to add, or press Cancel.",
                    buttons=cancel_keyboard(),
                )
                return

            if text.startswith("/addcomment "):
                comment = text.partition(" ")[2].strip()
                if not comment:
                    await show_controls(event, "Please provide comment text.")
                    return
                comments = load_comments()
                comments.append(comment)
                save_comments(comments)
                await show_controls(event, f"Comment added. Total: {len(comments)}")
                return

            if text == BUTTON_DELETE_COMMENT:
                comments = load_comments()
                if not comments:
                    await show_controls(event, "No comments to delete.")
                    return
                pending_actions[sender_id] = "delete_comment"
                listing = "\n".join(
                    f"{i + 1}. {comment}" for i, comment in enumerate(comments)
                )
                await event.respond(
                    f"Send the number to delete:\n\n{listing[:3500]}",
                    buttons=cancel_keyboard(),
                )
                return

            if text.startswith("/delcomment "):
                number = text.partition(" ")[2].strip()
                if not number.isdigit():
                    await show_controls(event, "Use /delcomment followed by a comment number.")
                    return
                idx = int(number) - 1
                comments = load_comments()
                if idx < 0 or idx >= len(comments):
                    await show_controls(event, f"Invalid number. Use 1 to {len(comments)}.")
                    return
                removed = comments.pop(idx)
                save_comments(comments)
                await show_controls(event, f"Removed comment: {removed}")
                return

            if text == BUTTON_SET_COOLDOWN:
                pending_actions[sender_id] = "set_cooldown"
                await event.respond(
                    "Send the cooldown in whole minutes (0 disables it; "
                    f"maximum {MAX_COOLDOWN_MINUTES}), or press Cancel.",
                    buttons=cancel_keyboard(),
                )
                return

            if text.startswith("/setdelay ") or text.startswith("/setcooldown "):
                minutes_text = text.partition(" ")[2].strip()
                if not minutes_text.isdigit() or int(minutes_text) > MAX_COOLDOWN_MINUTES:
                    await show_controls(
                        event,
                        f"Use /setdelay followed by 0 to {MAX_COOLDOWN_MINUTES} minutes.",
                    )
                    return
                cooldown_minutes = int(minutes_text)
                save_settings()
                await show_controls(
                    event,
                    f"Per-channel cooldown set to {cooldown_minutes} minute(s).",
                )
                return

            if text in {BUTTON_START_BOT, "/startbot"}:
                bot_running = True
                await show_controls(event, "Auto-commenting is now ON.")
                return

            if text in {BUTTON_STOP_BOT, "/stopbot"}:
                bot_running = False
                await show_controls(event, "Auto-commenting is now OFF.")
                return

            await show_controls(event, "Choose an action using the keyboard below.")

        bot_client.add_event_handler(
            handle_control_message, events.NewMessage(incoming=True)
        )

    logger.info(f"Listening for new channel posts. Auto-commenting: {'ON' if bot_running else 'OFF'}")

    tasks = [user_client.run_until_disconnected()]
    if bot_client:
        tasks.append(bot_client.run_until_disconnected())

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(run())
