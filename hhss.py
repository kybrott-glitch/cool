import os
import json
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = "8651176548:AAF0nHOk0HYSFcvkgToocRfVviPIRsaSXzE"
BOT_USERNAME = nft12bot

class EmojiStickerBot:
    def __init__(self):
        self.user_sessions = {}  # Store user sessions {user_id: {'emoji_set': {}, 'step': str}}
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a welcome message when /start is issued."""
        user = update.effective_user
        welcome_text = f"""
🎨 *Emoji to Sticker Pack Converter Bot*

Hi {user.first_name}! I can help you clone premium custom emojis and convert them into sticker packs.

*How to use:*
1️⃣ Send me a premium custom emoji
2️⃣ I'll analyze the emoji pack
3️⃣ Provide your custom sticker pack name
4️⃣ Get your converted sticker pack link!

*Commands:*
/start - Show this message
/help - Show help information
/cancel - Cancel current operation

*Note:* The bot needs to be added to your group with premium emoji access to see the emoji details.

Let's get started! Send me a premium custom emoji. 🚀
"""
        await update.message.reply_text(welcome_text, parse_mode='Markdown')
    
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send help message."""
        help_text = """
🤖 *Bot Help*

*What this bot does:*
- Clones premium custom emoji packs
- Converts them to standard sticker packs
- Gives you a shareable link

*Steps to use:*
1. Send a premium custom emoji (from any Telegram premium pack)
2. Reply with your desired sticker pack name
3. Wait while I convert the pack
4. Receive your sticker pack link!

*Commands:*
/start - Start the bot
/help - Show this help
/cancel - Cancel operation

*Requirements:*
- The bot must be in the same chat where the premium emoji is sent
- You need to have Telegram Premium to access premium emojis

*Note:* The emoji pack will be cloned and converted to a sticker pack. Your new pack will contain all emojis from the original pack converted to stickers.
"""
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel current operation."""
        user_id = update.effective_user.id
        if user_id in self.user_sessions:
            del self.user_sessions[user_id]
            await update.message.reply_text("✅ Operation cancelled. Send me a new premium emoji to start over!")
        else:
            await update.message.reply_text("No active operation to cancel.")
    
    async def handle_emoji(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle premium custom emoji messages."""
        user_id = update.effective_user.id
        message = update.message
        
        # Check if message contains a custom emoji
        if not message.entities:
            await message.reply_text("❌ Please send a premium custom emoji (from Telegram's premium emoji pack).")
            return
        
        # Look for custom_emoji entities
        emoji_data = None
        for entity in message.entities:
            if entity.type == "custom_emoji":
                emoji_data = {
                    'emoji_id': entity.custom_emoji_id,
                    'document_id': None
                }
                break
        
        if not emoji_data:
            await message.reply_text("❌ That doesn't look like a premium custom emoji. Please send a premium emoji from Telegram's emoji packs.")
            return
        
        # Try to get the emoji file
        try:
            # Get the custom emoji sticker
            custom_emoji = await context.bot.get_custom_emoji_stickers([emoji_data['emoji_id']])
            if custom_emoji:
                emoji_data['sticker'] = custom_emoji[0]
                emoji_data['set_name'] = custom_emoji[0].set_name
                emoji_data['emoji'] = custom_emoji[0].emoji
                
                # Get the sticker set information
                sticker_set = await context.bot.get_sticker_set(custom_emoji[0].set_name)
                emoji_data['sticker_set'] = sticker_set
                
                # Store session
                self.user_sessions[user_id] = {
                    'step': 'awaiting_pack_name',
                    'original_set': sticker_set,
                    'emoji_data': emoji_data
                }
                
                # Show pack info and ask for name
                pack_info = f"""
📦 *Emoji Pack Detected!*

*Pack Name:* `{sticker_set.name}`
*Title:* {sticker_set.title}
*Emojis in pack:* {len(sticker_set.stickers)}

Now, please send me your desired sticker pack name.
*Requirements:*
- Only English letters, numbers, and underscores
- Must start with a letter
- Cannot contain spaces
- Between 3-64 characters

Example: `my_cool_stickers_by_{BOT_USERNAME}`

Send /cancel to abort.
"""
                await message.reply_text(pack_info, parse_mode='Markdown')
                
        except Exception as e:
            logger.error(f"Error getting emoji pack: {e}")
            await message.reply_text("❌ Failed to analyze the emoji pack. Make sure the bot has access to the emoji and try again.")
    
    async def handle_pack_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the sticker pack name input."""
        user_id = update.effective_user.id
        message = update.message
        
        if user_id not in self.user_sessions:
            await message.reply_text("Please send a premium custom emoji first using /start.")
            return
        
        session = self.user_sessions[user_id]
        if session.get('step') != 'awaiting_pack_name':
            await message.reply_text("Please send a premium custom emoji first.")
            return
        
        pack_name = message.text.strip()
        
        # Validate pack name
        import re
        pattern = r'^[a-zA-Z][a-zA-Z0-9_]{2,63}$'
        if not re.match(pattern, pack_name):
            await message.reply_text("❌ Invalid pack name!\n\nRequirements:\n- Start with a letter\n- Only letters, numbers, underscores\n- 3-64 characters long\n\nTry again or send /cancel")
            return
        
        # Add bot username to avoid conflicts
        full_pack_name = f"{pack_name}_by_{BOT_USERNAME}"
        
        # Send processing message
        processing_msg = await message.reply_text("🔄 Cloning emoji pack and converting to stickers... This may take a few moments.")
        
        try:
            # Create new sticker pack
            original_set = session['original_set']
            stickers = original_set.stickers
            
            # Prepare sticker files for upload
            sticker_files = []
            for i, sticker in enumerate(stickers):
                # Download the sticker file
                file = await context.bot.get_file(sticker.file_id)
                file_path = f"temp_sticker_{i}.webp"
                await file.download_to_drive(file_path)
                sticker_files.append(file_path)
            
            # Create the sticker pack
            await context.bot.create_new_sticker_set(
                user_id=user_id,
                name=full_pack_name,
                title=f"{original_set.title} (Converted)",
                stickers=sticker_files,
                sticker_format="static"
            )
            
            # Send success message with link
            pack_link = f"https://t.me/addstickers/{full_pack_name}"
            success_msg = f"""
✅ *Success! Sticker Pack Created!*

🎉 Your sticker pack has been created successfully!

*Pack Name:* `{full_pack_name}`
*Number of stickers:* {len(stickers)}

🔗 *Click to add stickers:* [Add Sticker Pack]({pack_link})

💡 *Tip:* Share this link with friends to share the stickers!

Use /start to convert another emoji pack.
"""
            await processing_msg.edit_text(success_msg, parse_mode='Markdown', disable_web_page_preview=True)
            
            # Clean up temp files
            for file_path in sticker_files:
                if os.path.exists(file_path):
                    os.remove(file_path)
            
            # Clear session
            del self.user_sessions[user_id]
            
        except Exception as e:
            logger.error(f"Error creating sticker pack: {e}")
            error_msg = f"❌ Failed to create sticker pack: {str(e)}\n\nPossible reasons:\n- Pack name already exists\n- Invalid pack name format\n- Too many stickers in pack\n\nTry a different name or contact @{BOT_USERNAME} for help."
            await processing_msg.edit_text(error_msg)
            
            # Clean up temp files if any
            for file_path in sticker_files if 'sticker_files' in locals() else []:
                if os.path.exists(file_path):
                    os.remove(file_path)
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular text messages."""
        user_id = update.effective_user.id
        
        if user_id in self.user_sessions and self.user_sessions[user_id].get('step') == 'awaiting_pack_name':
            await self.handle_pack_name(update, context)
        else:
            await update.message.reply_text("Please send a premium custom emoji to get started, or use /help for assistance.")

def main():
    """Start the bot."""
    if not BOT_TOKEN:
        logger.error("No BOT_TOKEN found in environment variables!")
        print("Please set BOT_TOKEN in .env file")
        return
    
    # Create bot instance
    bot = EmojiStickerBot()
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help))
    application.add_handler(CommandHandler("cancel", bot.cancel))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
    application.add_handler(MessageHandler(filters.PHOTO | filters.ANIMATION | filters.STICKER, bot.handle_emoji))
    
    # Start bot
    print("🤖 Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
