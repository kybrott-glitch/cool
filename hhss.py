import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message

BOT_TOKEN = "8651176548:AAF0nHOk0HYSFcvkgToocRfVviPIRsaSXzE"

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

@dp.message(F.text)
async def convert_emoji(message: Message):
    if not message.entities:
        return

    for entity in message.entities:
        if entity.type == "custom_emoji":
            custom_emoji_id = entity.custom_emoji_id

            sticker = await bot.get_custom_emoji_stickers(
                custom_emoji_ids=[custom_emoji_id]
            )

            if not sticker:
                await message.reply("Failed to get emoji.")
                return

            await message.reply_sticker(sticker[0].file_id)
            return

    await message.reply("Send a Telegram custom emoji.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
