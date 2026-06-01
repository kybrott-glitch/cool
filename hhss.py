#!/usr/bin/env python3
"""
Telegram Bot: Premium Emoji → Animated Sticker Pack Converter
============================================================
Send any custom premium emoji to this bot and it will:
1. Detect the emoji's custom_emoji_id
2. Fetch all stickers in the same emoji pack
3. Create a new animated sticker pack (TGS format) under your bot
4. Reply with the pack name, link, and a summary

Requirements:
    pip install python-telegram-bot==20.* aiofiles aiohttp

Usage:
    1. Create a bot via @BotFather → get BOT_TOKEN
    2. Start the bot once yourself and send /start → get your OWNER_ID
       (or check via @userinfobot)
    3. Fill in BOT_TOKEN and OWNER_ID below, then run:
           python emoji_to_sticker_bot.py
"""

import asyncio
import logging
import os
import re
import sys
import time
from typing import Optional

# ──────────────────────────────────────────────
#  ⚙️  CONFIGURATION  – fill these in
# ──────────────────────────────────────────────
BOT_TOKEN: str = "8651176548:AAF0nHOk0HYSFcvkgToocRfVviPIRsaSXzE"      # from @BotFather
OWNER_ID:  int = 1899208318                           # your Telegram user ID (int)
# ──────────────────────────────────────────────

try:
    from telegram import (
        Update,
        InputSticker,
        Bot,
    )
    from telegram.ext import (
        Application,
        CommandHandler,
        MessageHandler,
        ContextTypes,
        filters,
    )
    import aiohttp
    import aiofiles
except ImportError:
    print(
        "\n[ERROR] Missing dependencies.\n"
        "Install them with:\n\n"
        "    pip install 'python-telegram-bot[job-queue]>=20.0' aiofiles aiohttp\n"
    )
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("EmojiStickerBot")

# ── helpers ──────────────────────────────────────────────────────────────────

def _safe_name(text: str) -> str:
    """Turn arbitrary text into a valid sticker-set short name segment."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", text)[:32].strip("_") or "pack"


async def _download_file(bot: Bot, file_id: str, dest: str) -> bool:
    """Download a Telegram file to *dest*.  Returns True on success."""
    try:
        tg_file = await bot.get_file(file_id)
        await tg_file.download_to_drive(dest)
        return True
    except Exception as exc:
        logger.warning("Download failed for %s: %s", file_id, exc)
        return False


async def _make_pack_name(bot_username: str, seed: str) -> str:
    """Build a unique sticker-set short name (≤ 64 chars, ends with _by_<bot>)."""
    ts   = str(int(time.time()))[-6:]          # last 6 digits of epoch
    slug = _safe_name(seed)[:20]
    return f"{slug}_{ts}_by_{bot_username}"


# ── /start ───────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 *Premium Emoji → Sticker Pack Bot*\n\n"
        "Send me any message that contains a *custom premium emoji* "
        "and I'll convert its entire emoji pack into a Telegram "
        "animated sticker pack for you!\n\n"
        "You can also prefix your message with a custom pack name, e.g.:\n"
        "`My Cool Pack <emoji>`",
        parse_mode="Markdown",
    )


# ── /help ─────────────────────────────────────────────────────────────────────

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "*How to use:*\n"
        "1. Send a message containing a custom premium Telegram emoji.\n"
        "2. Optionally add text before the emoji as the pack title.\n"
        "3. The bot fetches every emoji in that pack and creates a sticker set.\n"
        "4. You receive a direct link to your new sticker pack.\n\n"
        "*Notes:*\n"
        "• Only animated (TGS / video) custom emoji packs are supported.\n"
        "• Sticker sets are created under the *bot's* account – you can "
        "  add them to your favourites from the link.",
        parse_mode="Markdown",
    )


# ── main message handler ──────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return

    # ── 1. Find the first custom_emoji entity ────────────────────────────────
    entities = message.entities or []
    custom_emoji_id: Optional[str] = None
    for ent in entities:
        if ent.type == "custom_emoji":
            custom_emoji_id = ent.custom_emoji_id
            break

    if not custom_emoji_id:
        await message.reply_text(
            "⚠️ No custom premium emoji found in your message.\n"
            "Please send a message that *contains* a custom emoji.",
            parse_mode="Markdown",
        )
        return

    # ── 2. Derive a pack title from the message text (before the emoji) ──────
    plain_text = (message.text or "").strip()
    # Remove all custom-emoji characters to get the human-typed title
    title_candidate = re.sub(r"[\U00010000-\U0010ffff]", "", plain_text).strip()
    pack_title = title_candidate[:50] if title_candidate else "My Emoji Pack"

    status_msg = await message.reply_text("🔍 Fetching emoji info…")

    bot: Bot = context.bot

    # ── 3. Get the sticker set that owns this custom emoji ───────────────────
    try:
        stickers = await bot.get_custom_emoji_stickers([custom_emoji_id])
    except Exception as exc:
        await status_msg.edit_text(f"❌ Could not fetch emoji info: {exc}")
        return

    if not stickers:
        await status_msg.edit_text("❌ Could not retrieve sticker data for that emoji.")
        return

    source_sticker     = stickers[0]
    source_set_name: Optional[str] = source_sticker.set_name

    if not source_set_name:
        await status_msg.edit_text(
            "❌ This emoji doesn't belong to a named sticker set "
            "(it may be a standalone premium emoji)."
        )
        return

    await status_msg.edit_text(f"📦 Found pack `{source_set_name}`. Downloading stickers…", parse_mode="Markdown")

    # ── 4. Fetch all stickers in the source pack ─────────────────────────────
    try:
        source_set = await bot.get_sticker_set(source_set_name)
    except Exception as exc:
        await status_msg.edit_text(f"❌ Failed to load sticker set: {exc}")
        return

    all_stickers = source_set.stickers
    if not all_stickers:
        await status_msg.edit_text("❌ The source sticker set appears to be empty.")
        return

    # Determine sticker format from the first sticker's file type
    first = all_stickers[0]
    if first.is_animated:
        fmt = "animated"
    elif first.is_video:
        fmt = "video"
    else:
        fmt = "static"

    # ── 5. Download all sticker files ────────────────────────────────────────
    tmp_dir = f"/tmp/stickerpack_{int(time.time())}"
    os.makedirs(tmp_dir, exist_ok=True)

    downloaded: list[tuple[str, list[str]]] = []   # (local_path, [emoji])
    total = len(all_stickers)

    for idx, stk in enumerate(all_stickers, 1):
        ext = ".tgs" if stk.is_animated else (".webm" if stk.is_video else ".webp")
        dest = os.path.join(tmp_dir, f"sticker_{idx:03d}{ext}")
        ok   = await _download_file(bot, stk.file_id, dest)
        if ok:
            emojis = [stk.emoji] if stk.emoji else ["🌟"]
            downloaded.append((dest, emojis))
        if idx % 10 == 0 or idx == total:
            await status_msg.edit_text(
                f"⬇️ Downloading {idx}/{total} stickers…"
            )

    if not downloaded:
        await status_msg.edit_text("❌ No stickers could be downloaded.")
        return

    # ── 6. Build the new sticker pack ────────────────────────────────────────
    await status_msg.edit_text("🛠️ Creating your sticker pack…")

    bot_me       = await bot.get_me()
    bot_username = bot_me.username
    pack_short   = await _make_pack_name(bot_username, pack_title)

    # Prepare InputSticker list
    input_stickers = []
    for path, emojis in downloaded:
        async with aiofiles.open(path, "rb") as fh:
            data = await fh.read()
        input_stickers.append(
            InputSticker(sticker=data, emoji_list=emojis[:1], format=fmt)
        )

    # create_new_sticker_set requires user_id of the owner (must have started the bot)
    user_id = update.effective_user.id

    try:
        await bot.create_new_sticker_set(
            user_id=user_id,
            name=pack_short,
            title=pack_title,
            stickers=input_stickers[:50],  # Telegram max = 50 per creation call
        )
    except Exception as exc:
        err = str(exc)
        if "STICKERSET_INVALID" in err or "name is already occupied" in err.lower():
            # Append more stickers to an existing pack if name clash
            logger.info("Pack exists, will try adding stickers: %s", err)
        else:
            await status_msg.edit_text(f"❌ Failed to create sticker pack:\n`{err}`", parse_mode="Markdown")
            return

    # Add remaining stickers (51–200) in batches
    if len(input_stickers) > 50:
        await status_msg.edit_text("➕ Adding remaining stickers…")
        for stk in input_stickers[50:]:
            try:
                await bot.add_sticker_to_set(
                    user_id=user_id,
                    name=pack_short,
                    sticker=stk,
                )
            except Exception as exc:
                logger.warning("Could not add sticker: %s", exc)

    # ── 7. Clean up temp files ────────────────────────────────────────────────
    for path, _ in downloaded:
        try:
            os.remove(path)
        except OSError:
            pass
    try:
        os.rmdir(tmp_dir)
    except OSError:
        pass

    # ── 8. Reply with success ─────────────────────────────────────────────────
    pack_link = f"https://t.me/addstickers/{pack_short}"
    await status_msg.edit_text(
        f"✅ *Sticker pack created!*\n\n"
        f"📛 *Title:* {pack_title}\n"
        f"🔗 *Link:* {pack_link}\n"
        f"🎨 *Stickers:* {len(downloaded)} converted\n"
        f"📁 *Source pack:* `{source_set_name}`\n\n"
        f"Tap the link to add the pack to Telegram!",
        parse_mode="Markdown",
    )


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or OWNER_ID == 0:
        print(
            "\n[SETUP REQUIRED]\n"
            "Open this script and fill in:\n"
            "  BOT_TOKEN  – your bot token from @BotFather\n"
            "  OWNER_ID   – your Telegram numeric user ID\n"
        )
        sys.exit(1)

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help",  cmd_help))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message,
        )
    )

    logger.info("Bot is running. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
