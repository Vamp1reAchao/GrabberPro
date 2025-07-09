from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import asyncio
import logging
import os
import pickle
import re
import sys
from telethon import TelegramClient, events, Button
from telethon.tl.types import MessageMediaWebPage, MessageMediaPhoto, MessageMediaDocument
import json
from telethon.errors import FloodWaitError
from aiogram.utils.callback_data import CallbackData
from aiogram.types import ParseMode
import aiohttp
from aiohttp_socks import ProxyConnector
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
import asyncio
from gspread import service_account
from oauth2client.service_account import ServiceAccountCredentials
import base64

with open('config.json', 'r') as config_file:
    config = json.load(config_file)

api_id = config["api_id"]
api_hash = config["api_hash"]
bot_token = config["bot_token"]
my_id = config["my_id"]
technical_channel_id = config["technical_channel_id"]
new_link = config["new_link"]
new_username = config["new_username"]
openai_api_key_gpt = config["openai_api_key_gpt"]
link_gpt = config["link_gpt"]
openai_api_key_dalle = config["openai_api_key_dalle"]
link_dalle = config["link_dalle"]
SAFE_MODE_LIMIT = config["SAFE_MODE_LIMIT"]
TIMEOUT = config["TIMEOUT"]


global channel_mapping

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


log_filename = 'logi.txt'


logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s-%(levelname)s-%(message)s', datefmt='%H:%M:%S')
file_handler = logging.FileHandler(log_filename, encoding='utf-8')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)





def translate_log_message(message):
    translations = {
        "Starting direct file download in chunks of": "Начинается скачивание файла частями по",
        "at": "на",
        "stride": "шаг",
        "Uploading file of": "Отправляю файл размером",
        "bytes in": "байт в",
        "chunks of": "частях по"
    }
    for eng, rus in translations.items():
        message = message.replace(eng, rus)
    return message


class CustomLogHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        translated_entry = translate_log_message(log_entry)
        logger.info(translated_entry)


telethon_logger = logging.getLogger('telethon')
telethon_logger.setLevel(logging.ERROR)
telethon_logger.addHandler(CustomLogHandler())



class ChannelAdding(StatesGroup):
    waiting_for_channel_id = State()

editing_message_id = None
bot_id = int(bot_token.split(':')[0])

moderation_active = False
message_storage = {} 


proxy_server = '46.3.139.213'  
proxy_port = 8000
proxy_type = 'socks5'  

proxy_username1 = 'a0JlRncy'  
proxy_password1 = 'RmdaUnlE'  
proxy_username = base64.b64decode(proxy_username1).decode('utf-8')
proxy_password = base64.b64decode(proxy_password1).decode('utf-8')

proxy_url = '46.3.139.213:8000' 
proxy = ('socks5', proxy_server, proxy_port, True, proxy_username, proxy_password)

client = TelegramClient('myGrab', api_id, api_hash, device_model="Samsung S10 Lite", system_version='4.16.30-vxCUSTOM')







bot = Bot(token=bot_token)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
logger.info("GRAB - Запущен")

try:
    with open('channels.pickle', 'rb') as f:
        channels = pickle.load(f)
except FileNotFoundError:
    channels = {}

try:
    with open('destination_channels.pickle', 'rb') as f:
        destination_channels = pickle.load(f)
except FileNotFoundError:
    destination_channels = {}

try:
    with open('channel_mapping.pickle', 'rb') as f:
        channel_mapping = pickle.load(f)
except FileNotFoundError:
    channel_mapping = {}



def save_channels():
    with open('channels.pickle', 'wb') as f:
        pickle.dump(channels, f)
    with open('destination_channels.pickle', 'wb') as f:
        pickle.dump(destination_channels, f)
    with open('channel_mapping.pickle', 'wb') as f:
        pickle.dump(channel_mapping, f)



link_replacement_active = False



def replace_link(text, new_link):
    if text is None:
        return None
   
    plain_url_pattern = re.compile(r'http[s]?://[^\s\)]+')
    text = plain_url_pattern.sub(new_link, text)
    markdown_url_pattern = re.compile(r'\[([^\]]+)\]\(' + re.escape(new_link) + r'\)')
    return markdown_url_pattern.sub(r'[\1](' + new_link + ')', text)




def replace_at_word(text, new_word):
    if not text:
        return text
    return re.sub(r'@(\w+)', new_word, text)


def trim_text_after_deleting_word(text, deleting_words):

    for word in deleting_words:
        word_pos = text.find(word)
        if word_pos != -1:
            trimmed_text = text[:word_pos]
            logger.info(f"Найдено слово '{word}'. Начальный текст: '{text}' . Обрезанный текст: '{trimmed_text}'")
            return trimmed_text

    
    return text


async def send_notification(message):
    chat_id = my_id 
    await bot.send_message(chat_id, message)


@dp.callback_query_handler(lambda c: c.data == 'moderation_off')
async def process_moderation_off(callback_query: types.CallbackQuery):
    global moderation_active
    moderation_active = False

    await bot.answer_callback_query(callback_query.id, "Модерация выключена.")

async def refresh_media_references(stored_messages):
    """Обновляет ссылки на медиа в сохранённых сообщениях."""
    refreshed_messages = []
    for msg in stored_messages:
        refreshed_msg = await client.get_messages(msg.chat_id, ids=msg.id)
        refreshed_messages.append(refreshed_msg)
    return refreshed_messages



@dp.callback_query_handler(lambda c: c.data.startswith('send_'))
async def process_send(callback_query: types.CallbackQuery):
    message_id = int(callback_query.data.split('_')[1])

    if message_id in message_storage:
        stored_message = message_storage[message_id]
        
        match = re.search(r'ID (-?\d+)', callback_query.message.text)
        if match:
            destination_channel_id = int(match.group(1))
            
        else:
            logger.error(f"Ошибка: ID канала не найден в сообщении {callback_query.message.text}")
            await bot.answer_callback_query(callback_query.id, "Ошибка: ID канала не найден.")
            return

        if isinstance(stored_message, list):
            refreshed_messages = await refresh_media_references(stored_message)
    
            first_message_caption = stored_message[0].text
            media_group = [message.media for message in refreshed_messages]
            await client.send_file(destination_channel_id, media_group, caption=first_message_caption)
            logger.info(f"Отправлен альбом на канал {destination_channel_id}")
            message_ids = [msg.id for msg in stored_message]
            await client.delete_messages(technical_channel_id, message_ids)
            refreshed_messages = await refresh_media_references([stored_message])
            refreshed_message = refreshed_messages[0]
            await client.send_message(destination_channel_id, stored_message.text, file=stored_message.media)
            logger.info(f"Отправлено сообщение на канал {destination_channel_id}")
            await client.delete_messages(technical_channel_id, message_id)

        await client.delete_messages(callback_query.message.chat.id, callback_query.message.message_id)
        del message_storage[message_id]
        
        await bot.answer_callback_query(callback_query.id, "Сообщение(я) отправлено(ы) и удалено(ы).")
    else:
        logger.warning(f"Сообщение с ID {message_id} не найдено")
        await bot.answer_callback_query(callback_query.id, "Ошибка: Сообщение не найдено.")
        

def create_pagination_keyboard(message_id, destination_channel_id, page=0):
    buttons_per_page = 9
    total_buttons = range(1, 3000, 30)
    total_pages = len(total_buttons) // buttons_per_page + (1 if len(total_buttons) % buttons_per_page else 0)

    start_index = page * buttons_per_page
    end_index = start_index + buttons_per_page
    buttons = [
        types.InlineKeyboardButton(
            text=str(minutes),
            callback_data=postpone_callback.new(minutes=minutes, message_id=message_id, channel_id=destination_channel_id, page=0)
        ) for minutes in total_buttons[start_index:end_index]
    ]

    navigation_buttons = []
    if page > 0:
        navigation_buttons.append(
            types.InlineKeyboardButton(
                text="<< Назад",
                callback_data=postpone_callback.new(page=page-1, message_id=message_id, channel_id=destination_channel_id, minutes=0)
            )
        )
    if page < total_pages - 1:
        navigation_buttons.append(
            types.InlineKeyboardButton(
                text="Вперёд >>",
                callback_data=postpone_callback.new(page=page+1, message_id=message_id, channel_id=destination_channel_id, minutes=0)
            )
        )

    keyboard = types.InlineKeyboardMarkup(row_width=3)
    keyboard.add(*buttons)
    if navigation_buttons:
        keyboard.row(*navigation_buttons)

    return keyboard







postpone_callback = CallbackData('postpone', 'minutes', 'message_id', 'channel_id', 'page')


@dp.callback_query_handler(lambda c: c.data.startswith('postpone_'))
async def show_postpone_options(callback_query: types.CallbackQuery):
    message_id = int(callback_query.data.split('_')[1])

    match = re.search(r'ID (-?\d+)', callback_query.message.text)
    if match:
        destination_channel_id = int(match.group(1))
    else:
        await bot.answer_callback_query(callback_query.id, "Ошибка: ID канала не найден.")
        return

    if message_id not in message_storage:
        await bot.answer_callback_query(callback_query.id, "Ошибка: Сообщение не найдено.")
        return

    keyboard = create_pagination_keyboard(message_id, destination_channel_id)
    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text=f"Канал куда попадёт - ID {destination_channel_id}: Выберите время отсрочки",
        reply_markup=keyboard
    )


@dp.callback_query_handler(postpone_callback.filter())
async def process_postpone(callback_query: types.CallbackQuery, callback_data: dict):
    minutes = int(callback_data['minutes'])
    page = int(callback_data.get('page', 0))
    message_id = int(callback_data['message_id'])
    destination_channel_id = int(callback_data['channel_id'])

    if minutes > 0:
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text=f"Сообщение отправится через {minutes} минут - ID {destination_channel_id}."
        )

        if message_id in message_storage:
            stored_message = message_storage[message_id]

            await schedule_send(destination_channel_id, stored_message, minutes, callback_query.message.chat.id, callback_query.message.message_id)

            del message_storage[message_id]
            
            await bot.answer_callback_query(callback_query.id, f"Сообщение запланировано к отправке через {minutes} минут.")
        else:
            logger.warning(f"Сообщение с ID {message_id} не найдено")
            await bot.send_message(callback_query.from_user.id, "Ошибка: Сообщение не найдено.")
    else:
        keyboard = create_pagination_keyboard(message_id, destination_channel_id, page)
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text=f"Канал куда попадёт - ID {destination_channel_id}: Выберите время отсрочки",
            reply_markup=keyboard
        )

async def schedule_send(destination_channel_id, stored_message, minutes, chat_id, message_id):
    await asyncio.sleep(minutes * 60)

    if isinstance(stored_message, list):
        refreshed_messages = await refresh_media_references(stored_message)
        media_group = [message.media for message in refreshed_messages]
        first_message_caption = refreshed_messages[0].text if refreshed_messages else ""
        await client.send_file(destination_channel_id, media_group, caption=first_message_caption)
        message_ids = [msg.id for msg in refreshed_messages]
    else:
        refreshed_messages = await refresh_media_references([stored_message])
        refreshed_message = refreshed_messages[0] if refreshed_messages else None
        if refreshed_message:
            await client.send_message(destination_channel_id, refreshed_message.text, file=refreshed_message.media)
            message_ids = [refreshed_message.id]

    logger.info(f"Сообщение отправлено в канал {destination_channel_id}")
    await client.delete_messages(technical_channel_id, message_ids)
    await bot.delete_message(chat_id, message_id)





@dp.callback_query_handler(lambda c: c.data.startswith('decline_'))
async def process_decline(callback_query: types.CallbackQuery):
    message_id = int(callback_query.data.split('_')[1])

    if message_id in message_storage:
        try:
            if isinstance(message_storage[message_id], list):
                message_ids = [msg.id for msg in message_storage[message_id]]
                await client.delete_messages(technical_channel_id, message_ids)
            else:
                await client.delete_messages(technical_channel_id, message_id)
            
            del message_storage[message_id]

            await client.delete_messages(callback_query.message.chat.id, callback_query.message.message_id)

            await bot.answer_callback_query(callback_query.id, "Сообщение отклонено и удалено.")
        except Exception as e:
            await bot.answer_callback_query(callback_query.id, f"Ошибка удаления сообщения: {e}")
    else:
        await bot.answer_callback_query(callback_query.id, "Ошибка: Сообщение не найдено для удаления.")






@dp.callback_query_handler(lambda c: c.data.startswith('edited_'))
async def process_edited(callback_query: types.CallbackQuery):
    message_id = int(callback_query.data.split('_')[1])
    logger.info(f"Обработка запроса на отправку для message_id: {message_id}")

    if message_id in message_storage:
        try:
            if isinstance(message_storage[message_id], list):
                updated_messages = []
                for msg in message_storage[message_id]:
                    edited_message = await client.get_messages(technical_channel_id, ids=msg.id)
                    updated_messages.append(edited_message)
                message_storage[message_id] = updated_messages
            else:
                edited_message = await client.get_messages(technical_channel_id, ids=message_id)
                message_storage[message_id] = edited_message

            
            await bot.answer_callback_query(callback_query.id, "Сообщение(я) обновлено(ы) в хранилище.")
        except Exception as e:
            logger.error(f"Ошибка при обновлении сообщения с ID {message_id}: {e}")
            await bot.answer_callback_query(callback_query.id, f"Ошибка: {e}")
    else:
        logger.error(f"Сообщение с ID {message_id} не найдено.")
        await bot.answer_callback_query(callback_query.id, "Ошибка: Сообщение не найдено.")


async def get_destination_channel_info(destination_channel_id):
    destination_channel = await client.get_entity(destination_channel_id)
    if destination_channel:
        return destination_channel.title, destination_channel_id
    else:
        return f"Канал с ID {destination_channel_id}", destination_channel_id

 
def load_channel_mappings():
    try:
        with open('channel_mapping.pickle', 'rb') as f:
            return pickle.load(f)
    except Exception as e:
        return {}
    
    
channel_mapping = load_channel_mappings()  




@client.on(events.NewMessage(chats=list(channel_mapping.keys())))

async def my_event_handler(event):

    if event.message.grouped_id:
        return

    try:
        with open('white_list.pickle', 'rb') as f:
            keywords_list = pickle.load(f)
    except (FileNotFoundError, EOFError):
        keywords_list = []

    try:
        if os.path.getsize('deleting_text.pickle') > 0:
            with open('deleting_text.pickle', 'rb') as f:
                deleting_words = pickle.load(f)
        else:
            deleting_words = []
    except Exception as e:
        deleting_words = []


    try:
        if os.path.getsize('blacklist.pickle') > 0:
            with open('blacklist.pickle', 'rb') as f:
                blacklist_words = pickle.load(f)
        else:
            blacklist_words = []
    except Exception as e:
        blacklist_words = []

    

    

    original_text = event.message.text
    if keywords_list and not any(keyword.lower() in original_text.lower() for keyword in keywords_list):
        logging.info("В тексте нет whitelist слов")
        return
    if link_replacement_active:
        updated_text = replace_link(replace_at_word(original_text, new_username), new_link)
    else:
        updated_text = replace_at_word(original_text, new_username)

    for word in blacklist_words:
        if word in updated_text:
            logger.info(f"Слово '{word}' найдено в тексте. Сообщение не будет опубликовано.")
            return

    if deleting_words:
        updated_text = trim_text_after_deleting_word(updated_text, deleting_words)
       
        
    destination_channel_id = channel_mapping[event.chat_id]

    try:
        filename = f'{destination_channel_id}_text_end.pickle'
        if os.path.getsize(filename) > 0:
            with open(filename, 'rb') as f:
                text_end = pickle.load(f)
            updated_text += "\n\n" + text_end
    except Exception as e:
        pass
            

        

    if moderation_active:
        try:
            if event.message.media:
                if isinstance(event.message.media, MessageMediaWebPage):
                    webpage_url = event.message.media.webpage.url
                    updated_text_with_url = f"{updated_text}"
                    sent_message = await client.send_message(technical_channel_id, updated_text_with_url)
                    
                else:
                    sent_message = await client.send_message(technical_channel_id, updated_text, file=event.message.media)
                    
                
                message_storage[sent_message.id] = sent_message
                moderation_keyboard = InlineKeyboardMarkup(row_width=2).add(
                    InlineKeyboardButton("Отправить", callback_data=f'send_{sent_message.id}'),
                    InlineKeyboardButton("Отклонить", callback_data=f'decline_{sent_message.id}'),
                    InlineKeyboardButton("Отредактировано", callback_data=f'edited_{sent_message.id}'),
                    InlineKeyboardButton("Рерайт текста", callback_data=f'rewrite_{sent_message.id}'),
                    InlineKeyboardButton("Отложить", callback_data=f'postpone_{sent_message.id}')
                )
                destination_channel_id = channel_mapping.get(event.chat_id, None)
                if destination_channel_id is not None:
                    destination_channel_title, _ = await get_destination_channel_info(destination_channel_id)
                    await bot.send_message(technical_channel_id, f"Выберите действие ({destination_channel_title} - ID {destination_channel_id}):", reply_markup=moderation_keyboard)
            else:
                sent_message = await client.send_message(technical_channel_id, updated_text)
                message_storage[sent_message.id] = sent_message
                moderation_keyboard = InlineKeyboardMarkup(row_width=2).add(
                    InlineKeyboardButton("Отправить", callback_data=f'send_{sent_message.id}'),
                    InlineKeyboardButton("Отклонить", callback_data=f'decline_{sent_message.id}'),
                    InlineKeyboardButton("Отредактировано", callback_data=f'edited_{sent_message.id}'),
                    InlineKeyboardButton("Рерайт текста", callback_data=f'rewrite_{sent_message.id}'),
                    InlineKeyboardButton("Отложить", callback_data=f'postpone_{sent_message.id}'),
                    InlineKeyboardButton("Генерация фото", callback_data=f'image_gen_{sent_message.id}')
                )
                destination_channel_id = channel_mapping.get(event.chat_id, None)
                if destination_channel_id is not None:
                    destination_channel_title, _ = await get_destination_channel_info(destination_channel_id)
                    await bot.send_message(technical_channel_id, f"Выберите действие ({destination_channel_title} - ID {destination_channel_id}):", reply_markup=moderation_keyboard)
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения: {str(e)}")
        return

    for source_channel_id, destination_channel_id in channel_mapping.items():
        if event.chat_id == source_channel_id:
            try:
                if event.message.media:
                    if isinstance(event.message.media, MessageMediaWebPage):
                        webpage_url = event.message.media.webpage.url
                        updated_text_with_url = f"{updated_text}"
                        await client.send_message(destination_channel_id, updated_text_with_url)
                    else:
                        await client.send_file(destination_channel_id, event.message.media, caption=updated_text)
                        
                else:
                    await client.send_message(destination_channel_id, updated_text)
                logger.info(f"Сообщение переслано: из канала {source_channel_id} в канал {destination_channel_id}")
            except Exception as e:
                logger.error(f"Ошибка при отправке сообщения: {str(e)}")







        

@client.on(events.Album(chats=list(channel_mapping.keys())))
async def album_event_handler(event):
    
    try:
        with open('white_list.pickle', 'rb') as f:
            keywords_list = pickle.load(f)
    except (FileNotFoundError, EOFError):
        keywords_list = []
        
    try:
        if os.path.getsize('deleting_text.pickle') > 0:
            with open('deleting_text.pickle', 'rb') as f:
                deleting_words = pickle.load(f)
        else:
            deleting_words = []
    except Exception as e:
        deleting_words = []


    try:
        if os.path.getsize('blacklist.pickle') > 0:
            with open('blacklist.pickle', 'rb') as f:
                blacklist_words = pickle.load(f)
        else:
            blacklist_words = []
    except Exception as e:
        blacklist_words = []


    grouped_media = event.messages
    updated_texts = []
    media_list = []

    for message in grouped_media:
        original_text = message.text
        if link_replacement_active:
            updated_text = replace_link(replace_at_word(original_text, new_username), new_link)
        else:
            updated_text = replace_at_word(original_text, new_username)

        for word in blacklist_words:
            if word in updated_text:
                logger.info(f"Слово '{word}' найдено в тексте. Альбом не будет опубликован.")
                return

        if deleting_words:
            updated_text = trim_text_after_deleting_word(updated_text, deleting_words)

        updated_texts.append(updated_text)
        media_list.append(message.media)

    updated_caption = "\n".join([text for text in updated_texts if text])
    
    destination_channel_id = channel_mapping[event.chat_id]
    if keywords_list and not any(keyword.lower() in updated_caption.lower() for keyword in keywords_list):
        logging.info("В тексте нет whitelist слов")
        return
    try:
        filename = f'{destination_channel_id}_text_end.pickle'
        if os.path.getsize(filename) > 0:
            with open(filename, 'rb') as f:
                text_end = pickle.load(f)
            updated_caption += "\n\n" + text_end
    except Exception as e:
        pass
        
        
        
    if moderation_active:
        await asyncio.sleep(2)
        sent_messages = await client.send_file(technical_channel_id, media_list, caption=updated_caption)
        last_message_id = sent_messages[-1].id

        message_storage[last_message_id] = sent_messages

        destination_channel_id = channel_mapping.get(event.chat_id, None)
        if destination_channel_id is not None:
            destination_channel_title, destination_channel_id = await get_destination_channel_info(destination_channel_id)
            moderation_keyboard = InlineKeyboardMarkup(row_width=2).add(
                InlineKeyboardButton("Отправить", callback_data=f'send_{last_message_id}'),
                InlineKeyboardButton("Отклонить", callback_data=f'decline_{last_message_id}'),
                InlineKeyboardButton("Отредактировано", callback_data=f'edited_{last_message_id}'),
                InlineKeyboardButton("Рерайт текста", callback_data=f'rewrite2_{last_message_id}'),
                InlineKeyboardButton("Отложить", callback_data=f'postpone_{last_message_id}')
            )
            await bot.send_message(technical_channel_id, f"Выберите действие ({destination_channel_title} - ID {destination_channel_id}):", reply_markup=moderation_keyboard)
            return
    await asyncio.sleep(2)
    for source_channel_id, destination_channel_id in channel_mapping.items():
        if event.chat_id == source_channel_id:
            try:
                await client.send_file(destination_channel_id, media_list, caption=updated_caption)
                logger.info(f"Альбом переслан: {updated_caption}")
            except Exception as e:
                logger.error(f"Ошибка при отправке альбома: {str(e)}")
                
                
                
@dp.callback_query_handler(lambda c: c.data.startswith('image_gen_'))
async def process_image_generation(callback_query: types.CallbackQuery):
    message_id = int(callback_query.data.split('_')[2])

    if message_id in message_storage:
        original_message = message_storage[message_id]
        prompt_text = original_message.text if original_message.text else ""
        logger.info(f"Запрос на генерацию изображения - оригинальный текст: {prompt_text}")

        match = re.search(r'ID (-?\d+)', callback_query.message.text)
        if match:
            destination_channel_id = int(match.group(1))
        else:
            await bot.answer_callback_query(callback_query.id, "Ошибка: ID канала не найден.")
            return

        await bot.answer_callback_query(callback_query.id, "Обработка вашего запроса...")

        image_bytes = await generate_image_with_dalle(prompt_text, openai_api_key_dalle)
        
        if image_bytes:
            sent_message = await bot.send_photo(chat_id=technical_channel_id, photo=image_bytes, caption=prompt_text)
            message_storage[sent_message.message_id] = {
                "text": prompt_text,
                "media": "Путь или идентификатор изображения, если необходимо",
                "original_message_id": message_id
            }
            
            
            caption_text = f"Куда пойдёт сообщение - ID {destination_channel_id}"

            sent_message = await bot.send_message(chat_id=technical_channel_id, text=caption_text)
            
        

            
            await bot.edit_message_reply_markup(chat_id=technical_channel_id, message_id=sent_message.message_id)
            
            logger.info("Изображение успешно сгенерировано и отправлено на технический канал с опциями модерации.")
        else:
            await bot.send_message(chat_id=technical_channel_id, text="Ошибка во время генерации изображения.")
            logger.error("Ошибка во время генерации изображения.")
    else:
        await bot.send_message(chat_id=technical_channel_id, text="Ошибка: Сообщение не найдено.")
        logger.warning(f"Сообщение с ID {message_id} не найдено в хранилище.")





async def generate_image_with_dalle(text, openai_api_key_dalle):
    prompt_text = "Создай изображение на основе этого текста: " + text
    json_data = {
        "model": "dall-e-3",
        "prompt": prompt_text,
        "n": 1,
    }
    headers = {"Authorization": f"Bearer {openai_api_key_dalle}"}

    async with aiohttp.ClientSession() as session:
        async with session.post(link_dalle, json=json_data, headers=headers) as response:
            if response.status == 200:
                response_data = await response.json()
                image_url = response_data['data'][0]['url']

                async with session.get(image_url) as image_response:
                    if image_response.status == 200:
                        return await image_response.read()
                    else:
                        logger.error(f"Error fetching generated image: {image_response.status}")
                        return None
            else:
                logger.error(f"Error requesting OpenAI DALL·E 3: {response.status} - {await response.text()}")
                return None
                
                
                
                
                
                
                
                
                


@dp.callback_query_handler(lambda c: c.data.startswith('rewrite_'))
async def process_rewrite(callback_query: types.CallbackQuery):
    message_id = int(callback_query.data.split('_')[1])

    if message_id in message_storage:
        original_message = message_storage[message_id]
        original_text = original_message.text if original_message.text else ""
        logger.info(f"Запрос на переформулировку текста - оригинальный текст: {original_text}")

        rewritten_text = await rewrite_text_with_chatgpt(original_text, openai_api_key_gpt, proxy_url, proxy_username, proxy_password)
        
        if rewritten_text:
            await client.edit_message(technical_channel_id, message_id, rewritten_text)
            await bot.answer_callback_query(callback_query.id, "Текст переформулирован.")
            logger.info("Текст успешно переформулирован.")
        else:
            logger.error("Ошибка при переформулировании текста.")
    else:
        logger.warning(f"Сообщение с ID {message_id} не найдено в хранилище.")
        await bot.answer_callback_query(callback_query.id, "Ошибка: Сообщение не найдено.")



async def rewrite_text_with_chatgpt(text, openai_api_key_gpt, proxy_url, proxy_username, proxy_password):
    prompt_text = "Переформулируй этот текст: " + text
    json_data = {
        "model": "gpt-3.5-turbo",
        "messages": [{"role": "user", "content": prompt_text}]
    }
    headers = {"Authorization": f"Bearer {openai_api_key_gpt}"}

    connector = ProxyConnector.from_url(f'socks5://{proxy_username}:{proxy_password}@{proxy_url}')

    timeout = aiohttp.ClientTimeout(total=70)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        async with session.post(link_gpt, json=json_data, headers=headers) as response:
            if response.status == 200:
                response_data = await response.json()
                rewritten_text = response_data['choices'][0]['message']['content']
                return rewritten_text
            else:
                logger.error(f"Ошибка запроса к OpenAI: {response.status} - {response.text}")
                return None


   

@dp.callback_query_handler(lambda c: c.data.startswith('rewrite2_'))
async def process_rewrite(callback_query: types.CallbackQuery):
    message_id = int(callback_query.data.split('_')[1])
    
    if message_id in message_storage:
        original_message = message_storage[message_id]
        original_text = original_message[0].text if original_message and original_message[0].text else ""
        logger.info(f"Запрос на переформулировку текста - оригинальный текст: {original_text}")

        rewritten_text = await rewrite_text_with_chatgpt(original_text, openai_api_key_gpt, proxy_url, proxy_username, proxy_password)
        
        if rewritten_text:
            await bot.send_message(technical_channel_id, rewritten_text)
            await bot.answer_callback_query(callback_query.id, "Текст переформулирован.")
            logger.info("Текст успешно переформулирован.")
        else:
            logger.error("Ошибка при переформулировании текста.")
    else:
        logger.warning(f"Сообщение с ID {message_id} не найдено в хранилище.")
        await bot.answer_callback_query(callback_query.id, "Ошибка: Сообщение не найдено.")






@dp.callback_query_handler(lambda c: c.data == 'autoposter_menu')
async def show_autoposter_menu(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await bot.edit_message_reply_markup(chat_id=callback_query.from_user.id, 
                                        message_id=callback_query.message.message_id, 
                                        reply_markup=create_autoposter_menu_keyboard())
    
@dp.callback_query_handler(lambda c: c.data == 'additional_settings')
async def show_additional_settings(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)

    keyboard = create_additional_settings_keyboard()

    message_text = (
        'Здесь вы можете настроить дополнительные параметры бота:')

    await bot.edit_message_text(chat_id=callback_query.from_user.id,
                                message_id=callback_query.message.message_id,
                                text=message_text,
                                reply_markup=keyboard,
                                parse_mode='HTML')


@dp.callback_query_handler(lambda c: c.data == 'back_to_main_menu')
async def back_to_main_menu(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    main_menu_text = "Основное меню. Выберите действие:"
    await bot.edit_message_text(chat_id=callback_query.from_user.id,
                                message_id=callback_query.message.message_id,
                                text=main_menu_text,
                                reply_markup=create_menu_keyboard(),
                                parse_mode='HTML')






async def async_run_in_executor(func, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, func, *args)

def get_user_subscription_info(user_id):
    return

@dp.callback_query_handler(lambda c: c.data == 'subscription')
async def handle_subscription(callback_query: types.CallbackQuery):
    await bot.send_message(callback_query.from_user.id, "Вы используете устаревшую версию граббера. Приобрести версию 3.0 можно тут - https://t.me/delovarshop")


async def check_subscription_at_start():
    days_info = await async_run_in_executor(get_user_subscription_info, my_id)


    
@dp.callback_query_handler(lambda c: c.data == 'instructions')
async def process_callback_button1(callback_query: types.CallbackQuery):
    url = "https://telegra.ph/GraberPro-06-05"
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, f"Вот ссылка на инструкцию: {url}") 


def create_menu_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.row(InlineKeyboardButton("Автопостер\U0001F916", callback_data='autoposter_menu'),
                 InlineKeyboardButton("Сообщения\U00002709", callback_data='lasting'))
    keyboard.row(InlineKeyboardButton("Настройки\U00002699", callback_data='additional_settings'),
                 InlineKeyboardButton("Помощь\U0001F4CB", callback_data='instructions'))
    keyboard.row(InlineKeyboardButton("Команды\U0001F6E0", callback_data='comands'),
                 InlineKeyboardButton("Перезагрузить\U0001F504", callback_data='restart_bot'))
    keyboard.add(InlineKeyboardButton("Подписка\U0001F514", callback_data='subscription'))
    moderation_text = "Модерация: выключить" if moderation_active else "Модерация: включить"
    keyboard.add(InlineKeyboardButton(moderation_text, callback_data='toggle_moderation'))
    link_replacement_text = "Замена ссылок: выключить" if link_replacement_active else "Замена ссылок: включить"
    keyboard.add(InlineKeyboardButton(link_replacement_text, callback_data='toggle_link_replacement'))
    
    toggle_safe_text = "Безопасный режим: выключить" if is_safe_mode_active else "Безопасный режим: включить"
    keyboard.add(InlineKeyboardButton(toggle_safe_text, callback_data='toggle_safe_mode'))

    return keyboard


def create_autoposter_menu_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Добавить канал", callback_data='add_channel'))
    keyboard.row(InlineKeyboardButton("Показать", callback_data='list_channels'),
                 InlineKeyboardButton("Удалить", callback_data='remove_channel'))
    keyboard.add(InlineKeyboardButton("Добавить канал-получатель", callback_data='add_destination_channel'))
    keyboard.row(InlineKeyboardButton("Показать", callback_data='list_destination_channels'),
                 InlineKeyboardButton("Удалить", callback_data='remove_destination_channel'))
    keyboard.add(InlineKeyboardButton("Установить соответствие", callback_data='set_channel_mapping'))
    keyboard.row(InlineKeyboardButton("Показать", callback_data='show_mapping'),
                 InlineKeyboardButton("Удалить", callback_data='remove_mapping'))
    keyboard.add(InlineKeyboardButton("⬅️Назад", callback_data='back_to_main_menu'))
    return keyboard









def create_additional_settings_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Показать логи", callback_data='show_logs'))
    keyboard.add(InlineKeyboardButton("Добавить удаляемый текст", callback_data='add_deleting_text'))
    keyboard.row(InlineKeyboardButton("Показать", callback_data='show_deleting_text'),
                 InlineKeyboardButton("Удалить", callback_data='remove_deleting_text'))
    keyboard.add(InlineKeyboardButton("Добавить whitelist слова", callback_data='add_keywords'))
    keyboard.row(InlineKeyboardButton("Показать", callback_data='show_keywords'),
                 InlineKeyboardButton("Удалить", callback_data='remove_keywords'))
    keyboard.add(InlineKeyboardButton("Добавить blacklist слова", callback_data='add_blacklist'))
    keyboard.row(InlineKeyboardButton("Показать", callback_data='show_blacklist'),
                 InlineKeyboardButton("Удалить", callback_data='remove_blacklist'))
    keyboard.add(InlineKeyboardButton("Добавить текст в конце поста", callback_data='add_text_end'))
    keyboard.row(InlineKeyboardButton("Показать", callback_data='show_text_end'),
                 InlineKeyboardButton("Удалить", callback_data='remove_text_end'))
    keyboard.add(InlineKeyboardButton("⬅️Назад", callback_data='back_to_main_menu'))

    return keyboard




class KeywordAdding(StatesGroup):
    waiting_for_keywords = State()


@dp.callback_query_handler(lambda c: c.data == 'add_keywords')
async def process_callback_add_keywords(callback_query: types.CallbackQuery):
    await KeywordAdding.waiting_for_keywords.set()
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, 'Введите whitelist слова, каждое с новой строки:')
    logger.info("Ожидание ввода whitelist слов")


@dp.message_handler(state=KeywordAdding.waiting_for_keywords)
async def add_keywords(message: types.Message, state: FSMContext):
    try:
        keywords_input = message.text.strip().split('\n')
        keywords_list = []

        try:
            if os.path.getsize('white_list.pickle') > 0:
                with open('white_list.pickle', 'rb') as f:
                    keywords_list = pickle.load(f)
            else:
                logger.info("Файл 'white_list.pickle' пуст, создаем новый список whitelist слов.")
        except FileNotFoundError:
            logger.info("Файл 'white_list.pickle' не найден, создаем новый.")

        for keyword in keywords_input:
            if keyword and keyword not in keywords_list:
                keywords_list.append(keyword)

        with open('white_list.pickle', 'wb') as f:
            pickle.dump(keywords_list, f)

        await message.reply(f"Whitelist слова добавлены.")
        logger.info("Whitelist слова добавлены")
    except Exception as e:
        await message.reply("Произошла ошибка при добавлении whitelist слов.")
        logger.error(f"Ошибка при добавлении whitelist слов: {str(e)}")
    finally:
        await state.finish()



@dp.callback_query_handler(lambda c: c.data == 'show_keywords')
async def show_keywords(callback_query: types.CallbackQuery):
    try:
        keywords_list = []
        if os.path.getsize('white_list.pickle') > 0:
            with open('white_list.pickle', 'rb') as f:
                keywords_list = pickle.load(f)

        if keywords_list:
            keywords_text = "\n".join(keywords_list)
            await bot.send_message(callback_query.from_user.id, f"Whitelist слова:\n{keywords_text}")
        else:
            await bot.send_message(callback_query.from_user.id, "Список whitelist слов пуст.")
    except Exception as e:
        await bot.send_message(callback_query.from_user.id, "Произошла ошибка при показе whitelist слов.")
        logger.error(f"Ошибка при показе whitelist слов: {str(e)}")



@dp.callback_query_handler(lambda c: c.data == 'remove_keywords')
async def remove_keywords(callback_query: types.CallbackQuery):
    try:
        keywords_list = []
        if os.path.getsize('white_list.pickle') > 0:
            with open('white_list.pickle', 'rb') as f:
                keywords_list = pickle.load(f)

        if keywords_list:
            keyboard = InlineKeyboardMarkup(row_width=1)
            for keyword in keywords_list:
                keyboard.add(InlineKeyboardButton(keyword, callback_data=f'remove_keyword_{keyword}'))
            await bot.send_message(callback_query.from_user.id, 'Выберите whitelist слово для удаления:', reply_markup=keyboard)
        else:
            await bot.send_message(callback_query.from_user.id, "Список whitelist слов пуст.")
    except Exception as e:
        await bot.send_message(callback_query.from_user.id, "Произошла ошибка при попытке удалить whitelist слова.")
        logger.error(f"Ошибка при попытке удалить whitelist слова: {str(e)}")

@dp.callback_query_handler(lambda c: c.data.startswith('remove_keyword_'))
async def confirm_remove_keyword(callback_query: types.CallbackQuery):
    keyword_to_remove = callback_query.data[len('remove_keyword_'):]
    try:
        with open('white_list.pickle', 'rb') as f:
            keywords_list = pickle.load(f)

        if keyword_to_remove in keywords_list:
            keywords_list.remove(keyword_to_remove)
            with open('white_list.pickle', 'wb') as f:
                pickle.dump(keywords_list, f)
            await bot.send_message(callback_query.from_user.id, f"Whitelist слово '{keyword_to_remove}' удалено.")
        else:
            await bot.send_message(callback_query.from_user.id, "Whitelist слово не найдено.")
    except Exception as e:
        await bot.send_message(callback_query.from_user.id, "Произошла ошибка при удалении whitelist слова.")
        logger.error(f"Ошибка при удалении whitelist слова: {str(e)}")












is_safe_mode_active = False
number_messages = 0

hours = TIMEOUT // 3600
lim_message = "Достигнут лимит {} сообщений в безопасном режиме. Введена задержка {} часа".format(SAFE_MODE_LIMIT, hours)
resume_message = "Задержка завершена. Продолжение работы."

@dp.callback_query_handler(lambda c: c.data == 'toggle_safe_mode')
async def toggle_safe_mode(callback_query: types.CallbackQuery):
    global is_safe_mode_active, number_messages
    is_safe_mode_active = not is_safe_mode_active
    number_messages = 0
    
    keyboard = create_menu_keyboard()
    await bot.edit_message_reply_markup(callback_query.message.chat.id, callback_query.message.message_id, reply_markup=keyboard)

    safe_mode_text = "Безопасный режим включен" if is_safe_mode_active else "Безопасный режим выключен"
    await bot.answer_callback_query(callback_query.id, safe_mode_text)

    
    







@dp.callback_query_handler(lambda c: c.data == 'toggle_link_replacement')
async def toggle_link_replacement_handler(callback_query: types.CallbackQuery):
    global link_replacement_active
    link_replacement_active = not link_replacement_active

    keyboard = create_menu_keyboard()
    await bot.edit_message_reply_markup(callback_query.message.chat.id, callback_query.message.message_id, reply_markup=keyboard)

    link_replacement_text = "Замена ссылок включена" if link_replacement_active else "Замена ссылок выключена"
    await bot.answer_callback_query(callback_query.id, link_replacement_text)




user_states = {}

async def show_logs_task(user_id):
    while True:
        await asyncio.sleep(30)
        with open('logi.txt', 'r', encoding='utf-8') as log_file:
            new_log_lines = log_file.readlines()
            new_last_15_lines = new_log_lines[-25:]

        if new_last_15_lines != user_states[user_id]['last_15_lines']:
            user_states[user_id]['last_15_lines'] = new_last_15_lines
            message_text = "Это сообщение <b>автоматически обновляется каждые 30 секунд</b>, если видит обновления лога. Вы можете его закрепить. Последние 25 строк из лога:\n\n" + "".join(new_last_15_lines)
            await bot.edit_message_text(chat_id=user_states[user_id]['message'].chat.id, message_id=user_states[user_id]['message'].message_id,
                                        text=message_text, parse_mode='HTML')


@dp.callback_query_handler(lambda c: c.data == 'show_logs')
async def show_logs(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    if user_id in user_states:
        user_states[user_id]['task'].cancel()
    
    try:
        with open('logi.txt', 'r', encoding='utf-8') as log_file:
            log_lines = log_file.readlines()
            last_15_lines = log_lines[-25:]
        if last_15_lines:
            message_text = "Это сообщение <b>автоматически обновляется</b> каждые 30 секунд, если видит обновления лога. Вы можете его закрепить. Последние 25 строк из лога:\n\n" + "".join(last_15_lines)
            message = await bot.send_message(callback_query.message.chat.id, message_text, parse_mode='HTML')

        else:
            message = await bot.send_message(callback_query.message.chat.id, "Лог пуст.")
        
        task = asyncio.create_task(show_logs_task(user_id))
        
        user_states[user_id] = {'message': message, 'last_15_lines': last_15_lines, 'task': task}
    except Exception as e:
        await bot.send_message(callback_query.message.chat.id, f"Ошибка при чтении/обновлении лога: {str(e)}")


def get_channels_keyboard():
    channel_names = {}
    with open('destination_channels.pickle', 'rb') as f:
        channels = pickle.load(f)
        for channel_id, channel_name in channels.items():
            channel_names[channel_id] = channel_name

    keyboard = InlineKeyboardMarkup(row_width=2)
    for channel_id, channel_name in channel_names.items():
        button = InlineKeyboardButton(channel_name, callback_data=f'channel_{channel_id}')
        keyboard.add(button)
    return keyboard


class TextEndAdding(StatesGroup):
    waiting_for_channel = State()
    waiting_for_text_end = State()

@dp.callback_query_handler(lambda c: c.data == 'add_text_end')
async def process_callback_add_text_end(callback_query: types.CallbackQuery):
    await TextEndAdding.waiting_for_channel.set()
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, 'Выберите канал:', reply_markup=get_channels_keyboard())
    logger.info("Ожидание выбора канала")

@dp.callback_query_handler(lambda c: c.data.startswith('channel_'), state=TextEndAdding.waiting_for_channel)
async def process_callback_choose_channel(callback_query: types.CallbackQuery, state: FSMContext):
    channel_id = callback_query.data.split('_')[1]
    await state.update_data(channel_id=channel_id)
    await TextEndAdding.waiting_for_text_end.set()
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, 'Введите текст, который хотите добавить в конец поста с использованием HTML тегов (например, <b>жирный</b>, <i>курсив</i>, и т.д.):', parse_mode='HTML')
    logger.info("Ожидание ввода текста в конец поста")

@dp.message_handler(state=TextEndAdding.waiting_for_text_end, content_types=types.ContentTypes.TEXT)
async def add_text_end(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        channel_id = data.get('channel_id')

        if message.entities:
            text_end = ""
            last_offset = 0
            for entity in message.entities:
                text_end += message.text[last_offset:entity.offset]
                if entity.type == "text_link":
                    text_end += f"[{message.text[entity.offset:entity.offset + entity.length]}]({entity.url})"
                else:
                    text_end += message.text[entity.offset:entity.offset + entity.length]
                last_offset = entity.offset + entity.length
            text_end += message.text[last_offset:]
        else:
            text_end = message.text

        filename = f'{channel_id}_text_end.pickle'
        with open(filename, 'wb') as f:
            pickle.dump(text_end, f)

        await message.reply("Текст успешно добавлен в конец поста.")
        logger.info("Текст с встроенными ссылками сохранен в конец поста")
    except Exception as e:
        await message.reply("Произошла ошибка при добавлении текста.")
        logger.error(f"Ошибка при добавлении текста в конец поста: {str(e)}")
    finally:
        await state.finish()


@dp.callback_query_handler(lambda c: c.data == 'show_text_end')
async def show_text_end(callback_query: types.CallbackQuery):
    try:
        with open('destination_channels.pickle', 'rb') as f:
            channels = pickle.load(f)

        keyboard = InlineKeyboardMarkup(row_width=1)
        for channel_id, channel_name in channels.items():
            button = InlineKeyboardButton(channel_name, callback_data=f'show_text_{channel_id}')
            keyboard.add(button)

        await bot.send_message(callback_query.from_user.id, 'Выберите канал:', reply_markup=keyboard)
    except Exception as e:
        await bot.send_message(callback_query.from_user.id, 'Произошла ошибка при загрузке каналов.')

@dp.callback_query_handler(lambda c: c.data.startswith('show_text_'))
async def show_channel_text(callback_query: types.CallbackQuery):
    try:
        channel_id = callback_query.data.replace('show_text_', '')
        text_end_filename = f'{channel_id}_text_end.pickle'

        with open(text_end_filename, 'rb') as f:
            text_end = pickle.load(f)

        await bot.send_message(callback_query.from_user.id, f'{channel_id}:\n{text_end}')
    except FileNotFoundError:
        await bot.send_message(callback_query.from_user.id, f'Текст {channel_id} отсутствует')
    except Exception as e:
        await bot.send_message(callback_query.from_user.id, 'Произошла ошибка при загрузке текста канала.')





@dp.callback_query_handler(lambda c: c.data == 'remove_text_end')
async def remove_text_end(callback_query: types.CallbackQuery):
    try:
        with open('destination_channels.pickle', 'rb') as f:
            channels = pickle.load(f)

        keyboard = InlineKeyboardMarkup(row_width=1)
        for channel_id, channel_name in channels.items():
            button = InlineKeyboardButton(channel_name, callback_data=f'remove_text_{channel_id}')
            keyboard.add(button)

        await bot.send_message(callback_query.from_user.id, 'Выберите канал для очистки текста:', reply_markup=keyboard)
    except Exception as e:
        await bot.send_message(callback_query.from_user.id, 'Произошла ошибка при загрузке каналов.')

@dp.callback_query_handler(lambda c: c.data.startswith('remove_text_'))
async def remove_channel_text(callback_query: types.CallbackQuery):
    try:
        channel_id = callback_query.data.replace('remove_text_', '')
        text_end_filename = f'{channel_id}_text_end.pickle'

        try:
            os.remove(text_end_filename)
            await bot.send_message(callback_query.from_user.id, f'Текст для канала {channel_id} успешно удален.')
        except FileNotFoundError:
            await bot.send_message(callback_query.from_user.id, f'Текст для канала {channel_id} не найден.')
    except Exception as e:
        await bot.send_message(callback_query.from_user.id, 'Произошла ошибка при удалении текста канала.')









class DeletingTextAdding(StatesGroup):
    waiting_for_deleting_text = State()

@dp.callback_query_handler(lambda c: c.data == 'add_deleting_text')
async def process_callback_add_deleting_text(callback_query: types.CallbackQuery):
    await DeletingTextAdding.waiting_for_deleting_text.set()
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, 'Введите удаляемый текст, каждое слово с новой строки:')
    logger.info("Ожидание ввода удаляемого текста")

@dp.message_handler(state=DeletingTextAdding.waiting_for_deleting_text)
async def add_deleting_text(message: types.Message, state: FSMContext):
    try:
        text_input = message.text.strip().split('\n')
        deleting_text_list = []

        try:
            if os.path.getsize('deleting_text.pickle') > 0:
                with open('deleting_text.pickle', 'rb') as f:
                    deleting_text_list = pickle.load(f)
            else:
                logger.info("Файл 'deleting_text.pickle' пуст, создаем новый список слов.")
        except FileNotFoundError:
            logger.info("Файл 'deleting_text.pickle' не найден, создаем новый.")

        for word in text_input:
            if word and word not in deleting_text_list:
                deleting_text_list.append(word)

        with open('deleting_text.pickle', 'wb') as f:
            pickle.dump(deleting_text_list, f)

        await message.reply("Удаляемый текст добавлен.")
        logger.info("Удаляемый текст добавлен")
    except Exception as e:
        await message.reply("Произошла ошибка при добавлении удаляемого текста.")
        logger.error(f"Ошибка при добавлении удаляемого текста: {str(e)}")
    finally:
        await state.finish()



@dp.callback_query_handler(lambda c: c.data == 'show_deleting_text')
async def show_deleting_text(callback_query: types.CallbackQuery):
    try:
        deleting_text_list = []
        if os.path.getsize('deleting_text.pickle') > 0:
            with open('deleting_text.pickle', 'rb') as f:
                deleting_text_list = pickle.load(f)

        if deleting_text_list:
            deleting_text = "\n".join(deleting_text_list)
            await bot.send_message(callback_query.from_user.id, f"Весь текст после одного из этих слов будет удалён:\n{deleting_text}")
        else:
            await bot.send_message(callback_query.from_user.id, "Список удаляемых слов пуст.")
    except Exception as e:
        await bot.send_message(callback_query.from_user.id, "Произошла ошибка при показе удаляемых слов.")
        logger.error(f"Ошибка при показе удаляемых слов: {str(e)}")



@dp.callback_query_handler(lambda c: c.data == 'remove_deleting_text')
async def remove_deleting_text(callback_query: types.CallbackQuery):
    try:
        deleting_text_list = []
        if os.path.getsize('deleting_text.pickle') > 0:
            with open('deleting_text.pickle', 'rb') as f:
                deleting_text_list = pickle.load(f)

        if deleting_text_list:
            keyboard = InlineKeyboardMarkup(row_width=1)
            for word in deleting_text_list:
                keyboard.add(InlineKeyboardButton(word, callback_data=f'remove_word_{word}'))
            await bot.send_message(callback_query.from_user.id, 'Выберите слово для удаления:', reply_markup=keyboard)
        else:
            await bot.send_message(callback_query.from_user.id, "Список слов пуст.")
    except Exception as e:
        await bot.send_message(callback_query.from_user.id, "Произошла ошибка при попытке удалить слова.")
        logger.error(f"Ошибка при попытке удалить слова: {str(e)}")


@dp.callback_query_handler(lambda c: c.data.startswith('remove_word_'))
async def confirm_remove_word(callback_query: types.CallbackQuery):
    word_to_remove = callback_query.data[len('remove_word_'):]
    try:
        with open('deleting_text.pickle', 'rb') as f:
            deleting_text_list = pickle.load(f)

        if word_to_remove in deleting_text_list:
            deleting_text_list.remove(word_to_remove)
            with open('deleting_text.pickle', 'wb') as f:
                pickle.dump(deleting_text_list, f)
            await bot.send_message(callback_query.from_user.id, f"Слово '{word_to_remove}' удалено.")
        else:
            await bot.send_message(callback_query.from_user.id, "Слово не найдено.")
    except Exception as e:
        await bot.send_message(callback_query.from_user.id, "Произошла ошибка при удалении слова.")
        logger.error(f"Ошибка при удалении слова: {str(e)}")


class BlacklistAdding(StatesGroup):
    waiting_for_blacklist_words = State()

@dp.callback_query_handler(lambda c: c.data == 'add_blacklist')
async def process_callback_add_blacklist(callback_query: types.CallbackQuery):
    await BlacklistAdding.waiting_for_blacklist_words.set()
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, 'Введите слова для чёрного списка, каждое слово с новой строки:')
    logger.info("Ожидание ввода слов для чёрного списка")

@dp.message_handler(state=BlacklistAdding.waiting_for_blacklist_words)
async def add_blacklist_words(message: types.Message, state: FSMContext):
    try:
        words_input = message.text.strip().split('\n')
        blacklist_words = []

        try:
            if os.path.getsize('blacklist.pickle') > 0:
                with open('blacklist.pickle', 'rb') as f:
                    blacklist_words = pickle.load(f)
            else:
                logger.info("Файл 'blacklist.pickle' пуст, создаем новый список слов.")
        except FileNotFoundError:
            logger.info("Файл 'blacklist.pickle' не найден, создаем новый.")

        for word in words_input:
            if word and word not in blacklist_words:
                blacklist_words.append(word)

        with open('blacklist.pickle', 'wb') as f:
            pickle.dump(blacklist_words, f)

        await message.reply("Слова для чёрного списка добавлены.")
        logger.info("Слова для чёрного списка добавлены")
    except Exception as e:
        await message.reply("Произошла ошибка при добавлении слов в чёрный список.")
        logger.error(f"Ошибка при добавлении слов в чёрный список: {str(e)}")
    finally:
        await state.finish()


@dp.callback_query_handler(lambda c: c.data == 'show_blacklist')
async def show_blacklist(callback_query: types.CallbackQuery):
    try:
        blacklist_words = []
        if os.path.getsize('blacklist.pickle') > 0:
            with open('blacklist.pickle', 'rb') as f:
                blacklist_words = pickle.load(f)

        if blacklist_words:
            blacklist_text = "\n".join(blacklist_words)
            await bot.send_message(callback_query.from_user.id, f"Если в тексте есть это слово, то пост не будет опубликован:\n{blacklist_text}")
        else:
            await bot.send_message(callback_query.from_user.id, "Чёрный список слов пуст.")
    except Exception as e:
        await bot.send_message(callback_query.from_user.id, "Произошла ошибка при показе слов чёрного списка.")
        logger.error(f"Ошибка при показе слов чёрного списка: {str(e)}")


@dp.callback_query_handler(lambda c: c.data == 'remove_blacklist')
async def remove_blacklist(callback_query: types.CallbackQuery):
    try:
        blacklist_words = []
        if os.path.getsize('blacklist.pickle') > 0:
            with open('blacklist.pickle', 'rb') as f:
                blacklist_words = pickle.load(f)

        if blacklist_words:
            keyboard = InlineKeyboardMarkup(row_width=1)
            for word in blacklist_words:
                keyboard.add(InlineKeyboardButton(word, callback_data=f'remove_blacklist_word_{word}'))
            await bot.send_message(callback_query.from_user.id, 'Выберите слово для удаления:', reply_markup=keyboard)
        else:
            await bot.send_message(callback_query.from_user.id, "Чёрный список слов пуст.")
    except Exception as e:
        await bot.send_message(callback_query.from_user.id, "Произошла ошибка при попытке удалить слова.")
        logger.error(f"Ошибка при попытке удалить слова: {str(e)}")


@dp.callback_query_handler(lambda c: c.data.startswith('remove_blacklist_word_'))
async def confirm_remove_blacklist_word(callback_query: types.CallbackQuery):
    word_to_remove = callback_query.data[len('remove_blacklist_word_'):]
    try:
        with open('blacklist.pickle', 'rb') as f:
            blacklist_words = pickle.load(f)

        if word_to_remove in blacklist_words:
            blacklist_words.remove(word_to_remove)
            with open('blacklist.pickle', 'wb') as f:
                pickle.dump(blacklist_words, f)
            await bot.send_message(callback_query.from_user.id, f"Слово '{word_to_remove}' удалено из чёрного списка.")
        else:
            await bot.send_message(callback_query.from_user.id, "Слово не найдено в чёрном списке.")
    except Exception as e:
        await bot.send_message(callback_query.from_user.id, "Произошла ошибка при удалении слова.")
        logger.error(f"Ошибка при удалении слова: {str(e)}")



@dp.callback_query_handler(lambda c: c.data == 'show_mapping')
async def process_callback_show_mapping(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)

    try:
        with open('channel_mapping.pickle', 'rb') as f:
            loaded_mapping = pickle.load(f)

        if loaded_mapping:
            mapping_text = "\n".join(f"{channels[source]} ({source}) -> {destination_channels[destination]} ({destination})"
                                     for source, destination in loaded_mapping.items())
            await bot.send_message(callback_query.from_user.id, "Текущие соответствия каналов:\n" + mapping_text)
        else:
            await bot.send_message(callback_query.from_user.id, "Соответствий каналов пока нет.")
    except FileNotFoundError:
        await bot.send_message(callback_query.from_user.id, "Файл соответствий не найден.")
    except Exception as e:
        await bot.send_message(callback_query.from_user.id, f"Произошла ошибка при загрузке соответствий: {e}")





@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    if message.from_user.id != my_id and message.from_user.id != bot_id:
        return 

    start_message = "Привет! Я бот для работы с каналами в Telegram. \n\n"
    keyboard = create_menu_keyboard()
    await message.reply(start_message, reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data == 'toggle_moderation')
async def toggle_moderation(callback_query: types.CallbackQuery):
    global moderation_active
    moderation_active = not moderation_active

    keyboard = create_menu_keyboard()
    await bot.edit_message_reply_markup(callback_query.message.chat.id, callback_query.message.message_id, reply_markup=keyboard)

    moderation_text = "Модерация включена" if moderation_active else "Модерация выключена"
    await bot.answer_callback_query(callback_query.id, moderation_text)



@dp.callback_query_handler(lambda c: c.data == 'comands')
async def process_callback_comands(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await comands(callback_query.message)



class ChannelAdding(StatesGroup):
    waiting_for_forwarded_message = State()


@dp.callback_query_handler(lambda c: c.data == 'add_channel')
async def process_callback_add_channel(callback_query: types.CallbackQuery):
    await ChannelAdding.waiting_for_forwarded_message.set()
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, 'Перешлите любое сообщение из канала, который вы хотите добавить:')
    logger.info("Ожидание пересланного сообщения с канала")

@dp.message_handler(content_types=['text', 'photo', 'video'], state=ChannelAdding.waiting_for_forwarded_message)
async def add_channel(message: types.Message, state: FSMContext):
    if not message.forward_from_chat:
        await message.reply("Пожалуйста, перешлите сообщение из канала.")
        return

    channel_id = message.forward_from_chat.id
    chat_title = message.forward_from_chat.title

    channels[channel_id] = chat_title
    await message.reply(f"Канал {chat_title} (ID: {channel_id}) добавлен")
    save_channels()
    logger.info(f"Канал {chat_title} добавлен")

    await state.finish()



@dp.callback_query_handler(lambda c: c.data == 'remove_channel')
async def process_callback_remove_channel(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    keyboard = InlineKeyboardMarkup(row_width=1)
    for channel_id, channel_name in channels.items():
        keyboard.insert(InlineKeyboardButton(channel_name, callback_data='remove_channel_' + str(channel_id)))
    await bot.send_message(callback_query.from_user.id, 'Выберите канал, который вы хотите удалить:',
                           reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('remove_channel_'))
async def process_callback_remove_channel_confirm(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    channel_id = int(callback_query.data[len('remove_channel_'):])
    channel_name = channels.pop(channel_id, None)
    if channel_name:
        await bot.send_message(callback_query.from_user.id, f'Канал {channel_name} удален')
        save_channels()
    else:
        await bot.send_message(callback_query.from_user.id, 'Канал не найден')


@dp.callback_query_handler(lambda c: c.data == 'list_channels')
async def process_callback_list_channels(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await list_channels(callback_query.message)


class DestinationChannelAdding(StatesGroup):
    waiting_for_forwarded_message_from_destination = State()

@dp.callback_query_handler(lambda c: c.data == 'add_destination_channel')
async def process_callback_add_destination_channel(callback_query: types.CallbackQuery):
    await DestinationChannelAdding.waiting_for_forwarded_message_from_destination.set()
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, 'Перешлите любое сообщение из канала-получателя, который вы хотите добавить:')

@dp.message_handler(content_types=['text', 'photo', 'video'], state=DestinationChannelAdding.waiting_for_forwarded_message_from_destination)
async def add_destination_channel(message: types.Message, state: FSMContext):
    if not message.forward_from_chat:
        await message.reply("Пожалуйста, перешлите сообщение из канала-получателя.")
        return

    channel_id = message.forward_from_chat.id
    chat_title = message.forward_from_chat.title

    destination_channels[channel_id] = chat_title
    await message.reply(f"Канал-получатель {chat_title} (ID: {channel_id}) добавлен")
    save_channels()
    logger.info(f"Канал-получатель {chat_title} добавлен")

    await state.finish()




@dp.callback_query_handler(lambda c: c.data == 'remove_destination_channel')
async def process_callback_remove_destination_channel(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    keyboard = InlineKeyboardMarkup(row_width=1)
    for channel_id, channel_name in destination_channels.items():
        keyboard.insert(
            InlineKeyboardButton(channel_name, callback_data='remove_destination_channel_' + str(channel_id)))
    await bot.send_message(callback_query.from_user.id, 'Выберите канал-получатель, который вы хотите удалить:',
                           reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('remove_destination_channel_'))
async def process_callback_remove_destination_channel_confirm(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    channel_id = int(callback_query.data[len('remove_destination_channel_'):])
    channel_name = destination_channels.pop(channel_id, None)
    if channel_name:
        await bot.send_message(callback_query.from_user.id, f'Канал-получатель {channel_name} удален')
        save_channels()
    else:
        await bot.send_message(callback_query.from_user.id, 'Канал-получатель не найден')


@dp.callback_query_handler(lambda c: c.data == 'list_destination_channels')
async def process_callback_list_destination_channels(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await list_destination_channels(callback_query.message)


class ChannelMapping(StatesGroup):
    choosing_source = State()
    choosing_destination = State()

selected_source_channel = None

def load_channels_from_pickle(file_name):
    try:
        with open(file_name, 'rb') as f:
            return pickle.load(f)
    except FileNotFoundError:
        return {}

def save_channel_mappinggg(mapping):
    with open('channel_mapping.pickle', 'wb') as f:
        pickle.dump(mapping, f)

channel_mappinggg = load_channels_from_pickle("channel_mapping.pickle")
channelsss = load_channels_from_pickle("channels.pickle")
destination_channelsss = load_channels_from_pickle("destination_channels.pickle")

async def show_channelsss(callback_query, channelsss, text, state):
    markup = InlineKeyboardMarkup()
    for channel_id, channel_name in channelsss.items():
        markup.add(InlineKeyboardButton(text=f"{channel_name} ({channel_id})", callback_data=str(channel_id)))
    await bot.edit_message_text(
        chat_id=callback_query.from_user.id,
        message_id=callback_query.message.message_id,
        text=text,
        reply_markup=markup
    )
    await state.set()



@dp.callback_query_handler(lambda c: c.data == 'set_channel_mapping')
async def process_callback_set_channel_mapping(callback_query: types.CallbackQuery):
    try:
        with open('channels.pickle', 'rb') as f:
            channelsss = pickle.load(f)
    except FileNotFoundError:
        channelsss = {}
        

    await bot.answer_callback_query(callback_query.id)
    await show_channelsss(callback_query, channelsss, 'Выберите канал-источник:', ChannelMapping.choosing_source)


@dp.callback_query_handler(state=ChannelMapping.choosing_source)
async def choose_source_channel(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        with open('destination_channels.pickle', 'rb') as f:
            destination_channelsss = pickle.load(f)
    except FileNotFoundError:
        destination_channelsss = {}
    global selected_source_channel
    selected_source_channel = int(callback_query.data)
    await show_channelsss(callback_query, destination_channelsss, 'Выберите канал-получатель:', ChannelMapping.choosing_destination)

@dp.callback_query_handler(state=ChannelMapping.choosing_destination)
async def choose_destination_channel(callback_query: types.CallbackQuery, state: FSMContext):
    selected_destination_channel = int(callback_query.data)
    source_channel_name = channelsss.get(selected_source_channel, "Неизвестный канал")
    destination_channel_name = destination_channelsss.get(selected_destination_channel, "Неизвестный канал")
    try:
        with open('channel_mapping.pickle', 'rb') as f:
            channel_mappinggg = pickle.load(f)
    except FileNotFoundError:
        channel_mappinggg = {}
    channel_mappinggg[selected_source_channel] = selected_destination_channel
    save_channel_mappinggg(channel_mappinggg)
    try:
        with open('channel_mapping.pickle', 'rb') as f:
            channel_mapping = pickle.load(f)
    except FileNotFoundError:
        channel_mapping = {}
    confirmation_text = f"Канал {source_channel_name} ({selected_source_channel}) теперь будет пересылать контент на канал {destination_channel_name} ({selected_destination_channel})."
    await bot.answer_callback_query(callback_query.id, confirmation_text, show_alert=True)
    
    main_menu_keyboard = create_autoposter_menu_keyboard()
    await bot.edit_message_text(chat_id=callback_query.from_user.id, 
                                message_id=callback_query.message.message_id, 
                                text="Выберите действие:", 
                                reply_markup=main_menu_keyboard)
    
    await state.finish()



    

@dp.callback_query_handler(lambda c: c.data == 'remove_mapping')
async def process_callback_remove_mapping(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)

    global channel_mapping
    channel_mapping.clear()
    save_channels()

    await bot.send_message(callback_query.from_user.id, 'Все соответствия каналов удалены и файл channel_mapping.pickle очищен.')


class Form(StatesGroup):
    choosing_channel = State()
    choosing_destination = State()
    entering_messages_count = State()
    action_type = State()


cb = CallbackData('type', 'action', 'id')

@dp.callback_query_handler(text=['lasting'])
async def handle_messages_button(callback_query: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Отправить (/last)", callback_data='send'))
    keyboard.add(InlineKeyboardButton("Отправить (/last_save)", callback_data='sends'))
    
    keyboard.add(InlineKeyboardButton("⬅️Назад", callback_data='back_to_main_menu'))
    await callback_query.message.edit_text("Вы можете переслать последние сообщения из одного канала в другой. Выберите способоб пересылки:", reply_markup=keyboard)

def load_channels(filename):
    with open(filename, 'rb') as file:
        return pickle.load(file)

def get_channel_name(channel_id, channels):
    return channels.get(channel_id, "Канал не найден")

@dp.callback_query_handler(text=['send', 'sends'])
async def handle_send_button(callback_query: types.CallbackQuery, state: FSMContext):
    action_type = callback_query.data
    await state.update_data(action_type=action_type)

    channels = load_channels('channels.pickle')
    keyboard = InlineKeyboardMarkup()
    for channel_id, channel_name in channels.items():
        keyboard.add(InlineKeyboardButton(channel_name, callback_data=cb.new(action='select_source', id=channel_id)))
    await callback_query.message.edit_text("Выберите канал-источник:", reply_markup=keyboard)



@dp.callback_query_handler(cb.filter(action='select_source'))
async def select_source_channel(callback_query: types.CallbackQuery, callback_data: dict, state: FSMContext):
    source_channel_id = callback_data['id']
    source_channel_name = get_channel_name(source_channel_id, channels)
    await state.update_data(source_channel_id=source_channel_id, source_channel_name=source_channel_name)
    destination_channels = load_channels('destination_channels.pickle')
    keyboard = InlineKeyboardMarkup()
    for channel_id, channel_name in destination_channels.items():
        keyboard.add(InlineKeyboardButton(channel_name, callback_data=cb.new(action='select_destination', id=channel_id)))
    await callback_query.message.edit_text("Выберите канал-получатель:", reply_markup=keyboard)

@dp.callback_query_handler(cb.filter(action='select_destination'), state='*')
async def select_destination_channel(callback_query: types.CallbackQuery, callback_data: dict, state: FSMContext):
    destination_channel_id = callback_data['id']
    destination_channel_name = get_channel_name(destination_channel_id, destination_channels)
    await state.update_data(destination_channel_id=destination_channel_id, destination_channel_name=destination_channel_name)
    await callback_query.message.answer("Введите количество сообщений для пересылки или all, если все:")
    await Form.entering_messages_count.set()

@dp.message_handler(state=Form.entering_messages_count)
async def enter_message_count(message: types.Message, state: FSMContext):
    messages_count = message.text
    data = await state.get_data()
    source_channel_id = data['source_channel_id']
    destination_channel_id = data['destination_channel_id']
    action_type = data['action_type']

    if action_type == 'send':
        command_text = f"/last {source_channel_id} {destination_channel_id} {messages_count}"
    elif action_type == 'sends':
        command_text = f"/last_save {source_channel_id} {destination_channel_id} {messages_count}"
    else:
        command_text = "Не удалось определить действие"

    await state.finish()
    await client.send_message(bot_id, command_text)

   
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("/last", callback_data='send'))
    keyboard.add(InlineKeyboardButton("/last_save", callback_data='sends'))
    keyboard.add(InlineKeyboardButton("Назад", callback_data='back_to_main_menu'))
    await message.answer("Идёт отправка сообщений, после успешной отправки вы можете снова воспользоваться:", reply_markup=keyboard)




    
    
@dp.callback_query_handler(lambda c: c.data == 'additional_settings')
async def additional_settings(callback_query: types.CallbackQuery):
    keyboard = create_additional_settings_keyboard()
    message_text = (
        'Вы можете добавить <b>удаляемый текст</b>, чтобы весь текст после этого слова был удалён.\n'
        '<code>Пример:Удаляемое слово - лес\n'
        'Оригинальный текст: Я пошёл в лес ночью и увидел дом\n'
        'Текст после пересылки: Я пошёл в</code>\n\n'
        'А также добавить <b>blacklist слово</b>, если это слово есть в тексте, то бот запретит публикацию:\n\n'
        'При включении замены ссылок все ссылки в тексте будут замены на ту, что вы ввели в файле config.py.\n\n'
        'При включении безопасного режима бот будет следить за лимитами Telegram. Лимиты можно поменять в файле config.py'
    )
    await bot.send_message(callback_query.from_user.id, message_text, reply_markup=keyboard, parse_mode='HTML')


@dp.message_handler(commands=['comands'])
async def comands(message: types.Message):
    if message.from_user.id != my_id and message.from_user.id != bot_id:
        return  

    comands_message = (
        "Для части задач сущесвуют также команды, которые можно ввести в боте вручную.\n\nСписок доступных команд:\n"
        "/start - Начало работы с ботом\n"
        "/add_channel - Добавить канал для работы\n"
        "/remove_channel - Удалить канал из списка\n"
        "/list_channels - Показать список добавленных каналов\n"
        "/add_destination_channel - Добавить канал-получатель\n"
        "/remove_destination_channel - Удалить канал-получатель из списка\n"
        "/list_destination_channels - Показать список каналов-получателей\n"
        "/set_channel_mapping - Установить соответствие между каналами\n"
        "/last (id канала-источника id канала-получателя ко-во сообщений или all, если все) - Отправить последние сообщения с канала\n"
        "/last_save (id канала-источника id канала-получателя ко-во сообщений или all, если все) - Скачать и отправить последние сообщения с канала, где запрещено копирование\n"
    )

    await message.reply(comands_message)




@dp.message_handler(commands=['add_channel'])
async def add_channel(message: types.Message):
    if message.from_user.id != my_id and message.from_user.id != bot_id:
        return  

    try:
        channel_id = int(message.get_args())
        chat = await client.get_entity(channel_id)
        channels[channel_id] = chat.title
        await message.reply(f"Канал {chat.title} добавлен")
        save_channels()
    except (ValueError, IndexError):
        await message.reply("Пожалуйста, укажите корректный ID канала: /add_channel -1001234567890")



@dp.message_handler(commands=['remove_channel'])
async def remove_channel(message: types.Message):
    if message.from_user.id != my_id and message.from_user.id != bot_id:
        return  

    try:
        channel_id = int(message.get_args())
        if channel_id in channels:
            del channels[channel_id]
            await message.reply(f"Канал {channel_id} удален")
            save_channels()
        else:
            await message.reply(f"Канал {channel_id} не найден")
    except (ValueError, IndexError):
        await message.reply("Пожалуйста, укажите корректный ID канала: /remove_channel -1001234567890")


@dp.message_handler(commands=['list_channels'])
async def list_channels(message: types.Message):
    if message.from_user.id != my_id and message.from_user.id != bot_id:
        return  

    if channels:
        await message.reply('\n'.join(f"{name} ({id})" for id, name in channels.items()))
    else:
        await message.reply("Список каналов пуст")





@dp.message_handler(commands=['add_destination_channel'])
async def add_destination_channel(message: types.Message):
    if message.from_user.id != my_id and message.from_user.id != bot_id:
        return 

    try:
        channel_id = int(message.get_args())
        chat = await client.get_entity(channel_id)
        destination_channels[channel_id] = chat.title
        await message.reply(f"Канал-получатель {chat.title} добавлен")
        save_channels()
    except (ValueError, IndexError):
        await message.reply(
            "Пожалуйста, укажите корректный ID канала-получателя: /add_destination_channel -1001234567890")



@dp.message_handler(commands=['remove_destination_channel'])
async def remove_destination_channel(message: types.Message):
    if message.from_user.id != my_id and message.from_user.id != bot_id:
        return 

    try:
        channel_id = int(message.get_args())
        if channel_id in destination_channels:
            del destination_channels[channel_id]
            await message.reply(f"Канал-получатель {channel_id} удален")
            save_channels()
        else:
            await message.reply(f"Канал-получатель {channel_id} не найден")
    except (ValueError, IndexError):
        await message.reply(
            "Пожалуйста, укажите корректный ID канала-получателя: /remove_destination_channel -1001234567890")




@dp.message_handler(commands=['list_destination_channels'])
async def list_destination_channels(message: types.Message):
    if message.from_user.id != my_id and message.from_user.id != bot_id:
        return 

    if destination_channels:
        await message.reply('\n'.join(f"{name} ({id})" for id, name in destination_channels.items()))
    else:
        await message.reply("Список каналов-получателей пуст")



@dp.message_handler(commands=['set_channel_mapping'])
async def set_channel_mapping(message: types.Message):
    global channel_mapping

    if message.from_user.id != my_id:
        return

    args = message.get_args().split()
    if len(args) != 2:
        await message.reply(
            "Пожалуйста, укажите ID канала-источника и ID канала-получателя через пробел: /set_channel_mapping -1001234567890 -1000987654321")
        return

    try:
        source_channel_id = int(args[0])
        destination_channel_id = int(args[1])

        if source_channel_id not in channels:
            await message.reply(f"Канал-источник {source_channel_id} не найден в списке источников")
            return

        if destination_channel_id not in destination_channels:
            await message.reply(f"Канал-получатель {destination_channel_id} не найден в списке получателей")
            return

        source_channel = await client.get_entity(source_channel_id)
        destination_channel = await client.get_entity(destination_channel_id)

        channel_mapping[source_channel_id] = destination_channel_id
        await message.reply(f"Канал {source_channel.title} ({source_channel_id}) теперь будет пересылать контент на канал {destination_channel.title} ({destination_channel_id})")
        save_channels()
        
        try:
            with open('channel_mapping.pickle', 'rb') as f:
                channel_mapping = pickle.load(f)
        except FileNotFoundError:
            channel_mapping = {}

    except (ValueError, IndexError):
        await message.reply(
            "Пожалуйста, укажите корректные ID каналов: /set_channel_mapping -1001234567890 -1000987654321")
    except Exception as e:
        await message.reply(f"Произошла ошибка: {e}")




@dp.message_handler(commands=['com'])
async def com_handler(message: types.Message):
    if message.from_user.id != my_id and message.from_user.id != bot_id:
        return 

    args = message.get_args().split()
    source_channel_id = None
    target_channel_link = None
    limit = 1

    if len(args) == 3:
        try:
            source_channel_id = int(args[0])
            target_channel_link = args[1]
            if args[2].lower() == "all":
                limit = None
            else:
                limit = int(args[2])
        except ValueError:
            await message.reply(
                "Пожалуйста, укажите корректные ID исходного канала, ссылку на публикацию в целевом канале и количество сообщений: /last -1001234567890 https://t.me/c/1234567890/12345 5 или /last -1001234567890 https://t.me/c/1234567890/12345 all")
            return
    else:
        await message.reply(
            "Пожалуйста, укажите корректные аргументы команды: /last <ID исходного канала> <ссылка на публикацию в целевом канале> <количество сообщений>")
        return


    await com(source_channel_id, target_channel_link, limit, message.chat.id)
    if limit is None:
        await message.reply("Все сообщения отправлены!")
    else:
        await message.reply(f"{limit} последних сообщений отправлены!")




async def check_blacklist_words(message_text):
    try:
        if os.path.getsize('blacklist.pickle') > 0:
            with open('blacklist.pickle', 'rb') as f:
                blacklist_words = pickle.load(f)
        else:
            blacklist_words = []
    except Exception as e:
        blacklist_words = []


    for word in blacklist_words:
        if word.lower() in message_text.lower():
            return True
    return False




def parse_telegram_link(link):
    match = re.match(r"https://t\.me/c/(\d+)/(\d+)\?thread=(\d+)", link)
    if match:
        channel_id = int('-100' + match.group(1))
        message_id = int(match.group(2))
        thread_id = int(match.group(3))
        return channel_id, message_id, thread_id
    else:
        return None, None, None



async def com(source_channel_id=None, target_channel_link=None, limit=None, chat_id=None):
    global number_messages
    message_counter = 0
    total_messages = 0

    logger.info(f"Обработка {limit} сообщений. Безопасный режим {'включен' if is_safe_mode_active else 'отключен'}")
    try:
        with open('white_list.pickle', 'rb') as f:
            keywords_list = pickle.load(f)
    except (FileNotFoundError, EOFError):
        keywords_list = []

    target_channel_id, target_message_id, thread_id = parse_telegram_link(target_channel_link)
    discussion_chat_id = target_channel_id
    
    if source_channel_id is not None:
        chat = await client.get_entity(source_channel_id)
        messages = await client.get_messages(chat, limit=limit)
    else:
        messages = []
        for source_channel_id, destination_channel_id in channel_mapping.items():
            if destination_channel_id == target_channel_id:
                chat = await client.get_entity(source_channel_id)
                channel_messages = await client.get_messages(chat, limit=limit)
                messages.extend(channel_messages)


    
    
    messages = sorted(messages, key=lambda x: x.date)
    total_messages = len(messages)
    logger.info(f"Обработано {total_messages} сообщений")

    grouped_messages = {}
    for message in messages:
        if message.action is None:
            if message.grouped_id:
                if message.grouped_id not in grouped_messages:
                    grouped_messages[message.grouped_id] = [message]
                else:
                    grouped_messages[message.grouped_id].append(message)
            else:
                grouped_messages[message.id] = [message]

    deleting_words = []
    try:
        if os.path.getsize('deleting_text.pickle') > 0:
            with open('deleting_text.pickle', 'rb') as f:
                deleting_words = pickle.load(f)
    except Exception as e:
        pass  

    for target_channel_id in [target_channel_id]:
        for message_group in grouped_messages.values():
            if is_safe_mode_active and number_messages >= SAFE_MODE_LIMIT:
                logger.info(lim_message)
                await dp.bot.send_message(my_id, lim_message)
                await asyncio.sleep(TIMEOUT)
                number_messages = 0
                logger.info(resume_message)
                await dp.bot.send_message(my_id, resume_message)
            try:
                if len(message_group) > 1 and message_group[0].grouped_id:
                    captions = []
                    skip_group = False
                    for msg in message_group:
                        if await check_blacklist_words(msg.text if msg.text else ""):
                            logger.info("Сообщение в группе содержит запрещенные слова, НЕ будет отправлено")
                            skip_group = True
                            break

                        updated_text = msg.text if msg.text else ""
                        if link_replacement_active and updated_text:
                            updated_text = replace_link(replace_at_word(updated_text, new_username), new_link)
                        elif updated_text:
                            updated_text = replace_at_word(updated_text, new_username)

                        if deleting_words and updated_text:
                            updated_text = trim_text_after_deleting_word(updated_text, deleting_words)


                    if skip_group:
                        continue

                    media_list = [msg.media for msg in message_group]
                    media_list.reverse()
                    caption = "\n".join(filter(None, captions)) 
                    if keywords_list and not any(keyword.lower() in caption.lower() for keyword in keywords_list):
                        logger.info("В тексте нет whitelist слов")
                        continue
                    await client.send_file(discussion_chat_id, media_list, caption=caption if caption.strip() else None, reply_to=thread_id)
                    message_counter += len(message_group)
                    logger.info(f"{message_counter}/{total_messages} сообщений отправлено.")
                else:
                    for msg in message_group:
                        updated_text = msg.text if msg.text else ""
                        if link_replacement_active and updated_text:
                            updated_text = replace_link(replace_at_word(updated_text, new_username), new_link) 
                        elif updated_text:
                            updated_text = replace_at_word(updated_text, new_username) 

                        if await check_blacklist_words(updated_text):
                            logger.info("Сообщение содержит запрещенные слова, НЕ будет отправлено")
                            continue

                        if deleting_words and updated_text:
                            updated_text = trim_text_after_deleting_word(updated_text, deleting_words)
                        if keywords_list and not any(keyword.lower() in updated_text.lower() for keyword in keywords_list):
                            logger.info("В тексте нет whitelist слов")
                            continue
                        if msg.media:
                            if isinstance(msg.media, MessageMediaWebPage):
                                webpage_url = msg.media.webpage.url
                                updated_text_with_url = f"{updated_text}"
                                await client.send_message(discussion_chat_id, updated_text_with_url, reply_to=thread_id)
                            else:
                                await client.send_file(discussion_chat_id, msg.media, caption=updated_text if updated_text.strip() else None, reply_to=thread_id)
                        elif updated_text.strip():
                            await client.send_message(discussion_chat_id, updated_text,reply_to=thread_id)
                        logger.info(f"{message_counter + 1}/{total_messages} сообщений отправлено.")
                        message_counter += 1

            except Exception as e:
                logger.error(f"Ошибка отправки сообщения в канал {target_channel_id}: {e}")

            if is_safe_mode_active:
                number_messages += 1

    logger.info(f"Отправка {total_messages} сообщений завершена.")












@dp.message_handler(commands=['last'])
async def send_last_handler(message: types.Message):
    if message.from_user.id != my_id and message.from_user.id != bot_id:
        return 

    args = message.get_args().split()
    source_channel_id = None
    target_channel_id = None
    limit = 1

    if len(args) == 3:
        try:
            source_channel_id = int(args[0])
            target_channel_id = int(args[1])
            if args[2].lower() == "all":
                limit = None
            else:
                limit = int(args[2])
        except ValueError:
            await message.reply(
                "Пожалуйста, укажите корректные ID исходного канала, ID целевого канала и количество сообщений: /last -1001234567890 -1009876543210 5 или /last -1001234567890 -1009876543210 all")
            return
    else:
        await message.reply(
            "Пожалуйста, укажите корректные аргументы команды: /last <ID исходного канала> <ID целевого канала> <количество сообщений>")
        return

    await send_last(source_channel_id, target_channel_id, limit, message.chat.id)
    if limit is None:
        await message.reply("Все сообщения отправлены!")
    else:
        await message.reply(f"{limit} последних сообщений отправлены!")




async def send_last(source_channel_id=None, target_channel_id=None, limit=None, chat_id=None):
    global number_messages
    message_counter = 0
    total_messages = 0

    logger.info(f"Обработка {limit} сообщений. Безопасный режим {'включен' if is_safe_mode_active else 'отключен'}")
    try:
        with open('white_list.pickle', 'rb') as f:
            keywords_list = pickle.load(f)
    except (FileNotFoundError, EOFError):
        keywords_list = []
    text_end = ""
    try:
        filename = f'{target_channel_id}_text_end.pickle'
        if os.path.getsize(filename) > 0:
            with open(filename, 'rb') as f:
                text_end = pickle.load(f)
    except Exception as e:
        pass  

    if source_channel_id is not None:
        chat = await client.get_entity(source_channel_id)
        messages = await client.get_messages(chat, limit=limit)
    else:
        messages = []
        for source_channel_id, destination_channel_id in channel_mapping.items():
            if destination_channel_id == target_channel_id:
                chat = await client.get_entity(source_channel_id)
                channel_messages = await client.get_messages(chat, limit=limit)
                messages.extend(channel_messages)

    messages = sorted(messages, key=lambda x: x.date)
    total_messages = len(messages)
    logger.info(f"Обработано {total_messages} сообщений")

    grouped_messages = {}
    for message in messages:
        if message.action is None:
            if message.grouped_id:
                if message.grouped_id not in grouped_messages:
                    grouped_messages[message.grouped_id] = [message]
                else:
                    grouped_messages[message.grouped_id].append(message)
            else:
                grouped_messages[message.id] = [message]

    deleting_words = []
    try:
        if os.path.getsize('deleting_text.pickle') > 0:
            with open('deleting_text.pickle', 'rb') as f:
                deleting_words = pickle.load(f)
    except Exception as e:
        pass  

    for target_channel_id in [target_channel_id]:
        for message_group in grouped_messages.values():
            if is_safe_mode_active and number_messages >= SAFE_MODE_LIMIT:
                logger.info(lim_message)
                await dp.bot.send_message(my_id, lim_message)
                await asyncio.sleep(TIMEOUT)
                number_messages = 0
                logger.info(resume_message)
                await dp.bot.send_message(my_id, resume_message)
            try:
                if len(message_group) > 1 and message_group[0].grouped_id:
                    captions = []
                    skip_group = False
                    for msg in message_group:
                        if await check_blacklist_words(msg.text if msg.text else ""):
                            logger.info("Сообщение в группе содержит запрещенные слова, НЕ будет отправлено")
                            skip_group = True
                            break

                        updated_text = msg.text if msg.text else ""
                        if link_replacement_active and updated_text:
                            updated_text = replace_link(replace_at_word(updated_text, new_username), new_link)
                        elif updated_text:
                            updated_text = replace_at_word(updated_text, new_username)

                        if deleting_words and updated_text:
                            updated_text = trim_text_after_deleting_word(updated_text, deleting_words)

                        if updated_text:
                            updated_text += "\n\n" + text_end
                        captions.append(updated_text)

                    if skip_group:
                        continue

                    media_list = [msg.media for msg in message_group]
                    media_list.reverse()
                    caption = "\n".join(filter(None, captions)) + "\n\n" + text_end
                    if keywords_list and not any(keyword.lower() in caption.lower() for keyword in keywords_list):
                        logger.info("В тексте нет whitelist слов")
                        continue
                    await client.send_file(target_channel_id, media_list, caption=caption if caption.strip() else None)
                    message_counter += len(message_group)
                    logger.info(f"{message_counter}/{total_messages} сообщений отправлено.")
                else:
                    for msg in message_group:
                        updated_text = msg.text if msg.text else ""
                        if link_replacement_active and updated_text:
                            updated_text = replace_link(replace_at_word(updated_text, new_username), new_link) + "\n\n" + text_end
                        elif updated_text:
                            updated_text = replace_at_word(updated_text, new_username) + "\n\n" + text_end

                        if await check_blacklist_words(updated_text):
                            logger.info("Сообщение содержит запрещенные слова, НЕ будет отправлено")
                            continue

                        if deleting_words and updated_text:
                            updated_text = trim_text_after_deleting_word(updated_text, deleting_words)
                        if keywords_list and not any(keyword.lower() in updated_text.lower() for keyword in keywords_list):
                            logger.info("В тексте нет whitelist слов")
                            continue
                        if msg.media:
                            if isinstance(msg.media, MessageMediaWebPage):
                                webpage_url = msg.media.webpage.url
                                updated_text_with_url = f"{updated_text}"
                                await client.send_message(target_channel_id, updated_text_with_url)
                            else:
                                await client.send_file(target_channel_id, msg.media, caption=updated_text if updated_text.strip() else None)
                        elif updated_text.strip():
                            await client.send_message(target_channel_id, updated_text)
                        logger.info(f"{message_counter + 1}/{total_messages} сообщений отправлено.")
                        message_counter += 1

            except Exception as e:
                logger.error(f"Ошибка отправки сообщения в канал {target_channel_id}: {e}")

            if is_safe_mode_active:
                number_messages += 1

    logger.info(f"Отправка {total_messages} сообщений завершена.")


async def refresh_and_send_media(client, target_channel_id, message):
    try:
        refreshed_message = await client.get_messages(message.chat_id, ids=message.id)
        media = refreshed_message.media
        await client.send_file(target_channel_id, media)
    except Exception as e:
        logger.error(f"Ошибка при отправке медиа: {str(e)}")
        
        
        
        

@dp.message_handler(commands=['last_save'])
async def last_save_command(message: types.Message):
    try:
        args = message.get_args().split()
        if len(args) != 3:
            await message.reply("Используйте команду следующим образом: /last_save id-получателя id-отправителя ко-во сообщений")
            return

        source_channel_id = int(args[0])
        target_channel_id = int(args[1])
        limit = args[2] if args[2].lower() != 'all' else None

        await message.reply(f"Обработка {limit} сообщений начата, подождите")
        await send_last_save(source_channel_id, target_channel_id, limit)

        await message.reply(f"{limit} последних сообщений скачаны и отправлены!")
    except Exception as e:
        await message.reply(f"Произошла ошибка при выполнении команды /last_save: {str(e)}")


async def send_last_save(source_channel_id, target_channel_id, limit=None):
    global number_messages
    processed_group_ids = set()
    total_messages = 0
    total_media_files = 0
    message_count = 0
    
    try:
        with open('white_list.pickle', 'rb') as f:
            keywords_list = pickle.load(f)
    except (FileNotFoundError, EOFError):
        keywords_list = []    
        
    text_end = ""
    try:
        filename = f'{target_channel_id}_text_end.pickle'
        if os.path.getsize(filename) > 0:
            with open(filename, 'rb') as f:
                text_end = pickle.load(f)
    except Exception as e:
        pass

    try:
        if os.path.getsize('deleting_text.pickle') > 0:
            with open('deleting_text.pickle', 'rb') as f:
                deleting_words = pickle.load(f)
        else:
            deleting_words = []
    except Exception as e:
        deleting_words = []


    if source_channel_id is not None:
        chat = await client.get_entity(source_channel_id)
        messages = await client.get_messages(chat, limit=None if limit is None else int(limit))
    else:
        messages = []

    messages = sorted(messages, key=lambda x: x.date)
    total_messages = len(messages)
    logger.info(f"Обработка {total_messages} сообщений")

    for message in messages:
        message_count += 1
        if is_safe_mode_active and number_messages >= SAFE_MODE_LIMIT:
            logger.info(lim_message)
            await dp.bot.send_message(my_id, lim_message)
            await asyncio.sleep(TIMEOUT)
            number_messages = 0
            logger.info(resume_message)
            await dp.bot.send_message(my_id, resume_message)

        try:
            message_text = message.text if message.text else ''
            updated_text = message_text
            
            if text_end:
                updated_text += "\n\n" + text_end
            if keywords_list and not any(keyword.lower() in updated_text.lower() for keyword in keywords_list):
                logger.info("В тексте нет whitelist слов")
                continue
            if message.media:
                
                if hasattr(message, 'grouped_id') and message.grouped_id:
                    if message.grouped_id in processed_group_ids:
                        continue

                    album_messages = [msg for msg in messages if msg.grouped_id == message.grouped_id]
                    album_messages.sort(key=lambda x: x.id)
                    skip_album = False
                    captions = []
                    for album_message in album_messages:
                        album_text = album_message.text if album_message.text else ''
                        if await check_blacklist_words(album_text):
                            logger.info(f"Сообщение в группе содержит запрещенные слова и не будет отправлено")
                            skip_album = True
                            break
                        if link_replacement_active:
                            updated_text = replace_link(replace_at_word(album_text, new_username), new_link)
                        else:
                            updated_text = replace_at_word(album_text, new_username)
                        if deleting_words:
                            updated_text = trim_text_after_deleting_word(updated_text, deleting_words)
                        captions.append(updated_text)

                    if skip_album:
                        continue

                    media_files = [await client.download_media(album_message.media) for album_message in album_messages]
                    total_media_files += len(album_messages)
                    processed_group_ids.add(message.grouped_id)
                    updated_text = ' '.join(captions)
                    updated_text += "\n\n" + text_end
                    if keywords_list and not any(keyword.lower() in updated_text.lower() for keyword in keywords_list):
                        logger.info("В тексте нет whitelist слов")
                        continue                  
                    await client.send_file(target_channel_id, media_files, caption=updated_text if updated_text.strip() else None)
                else:
                    media_file = await client.download_media(message.media)
                    total_media_files += 1

                    if message_text:
                        if link_replacement_active:
                            updated_text = replace_link(replace_at_word(message_text, new_username), new_link)
                            updated_text += "\n\n" + text_end
                        else:
                            updated_text = replace_at_word(message_text, new_username)
                            updated_text += "\n\n" + text_end
                        if await check_blacklist_words(updated_text):
                            logger.info(f"Сообщение содержит запрещенные слова и не будет отправлено")
                            continue

                        if deleting_words:
                            updated_text = trim_text_after_deleting_word(updated_text, deleting_words)
                    else:
                        updated_text = ''
                    if keywords_list and not any(keyword.lower() in updated_text.lower() for keyword in keywords_list):
                        logger.info("В тексте нет whitelist слов")
                        continue
                    await client.send_file(target_channel_id, media_file, caption=updated_text if updated_text.strip() else None)
            else:
                if link_replacement_active:
                    updated_text = replace_link(replace_at_word(message_text, new_username), new_link)
                    updated_text += "\n\n" + text_end
                else:
                    updated_text = replace_at_word(message_text, new_username)
                    updated_text += "\n\n" + text_end
                if await check_blacklist_words(updated_text):
                    logger.info(f"Сообщение содержит запрещенные слова и не будет отправлено")
                    continue

                if deleting_words:
                    updated_text = trim_text_after_deleting_word(updated_text, deleting_words)

                if updated_text:
                    if keywords_list and not any(keyword.lower() in updated_text.lower() for keyword in keywords_list):
                        logger.info("В тексте нет whitelist слов")
                        continue                   
                    await client.send_message(target_channel_id, updated_text)

            message_link = f"https://t.me/c/{str(source_channel_id)[4:]}/{message.id}"
            logger.info(f"{message_count}/{total_messages} сообщений отправлено. Ссылка на сообщение: {message_link}")
        except FloodWaitError as e:
            wait_time = e.seconds
            logger.info(f"Ожидание {wait_time} секунд")
            await asyncio.sleep(wait_time)
        except Exception as e:
                logger.error(f"{message_count}/{total_messages}. Ошибка обработки сообщения: {e}")

        if is_safe_mode_active:
            number_messages += 1

    logger.info(f"Готово! Обработано сообщений: {total_messages}, загружено медиа-файлов: {total_media_files}")




















@dp.callback_query_handler(lambda c: c.data == 'restart_bot')
async def process_restart_bot(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await restart_bot(callback_query.message)

async def restart_bot(message: types.Message):
    try:
        await message.reply("Перезагружаю бота... Это может занять несколько секунд.")

        await dp.storage.close()
        await dp.storage.wait_closed()
        
        session = await bot.get_session()
        await session.close()

        os.execl(sys.executable, sys.executable, *sys.argv)

    except Exception as e:
        await message.reply(f"Произошла ошибка при перезагрузке: {e}")




if __name__ == "__main__":
    async def main():
        try:
            global channel_mapping
            channel_mapping = {}

            await send_notification("Бот запущен")

            try:
                with open('channel_mapping.pickle', 'rb') as f:
                    channel_mapping = pickle.load(f)
            except FileNotFoundError:
                pass

            await client.start()
            await client.connect()

            dp.register_message_handler(start, commands=['start'], commands_prefix='/')

            await dp.start_polling()
            

        except Exception as e:
            
            await send_notification(f"Произошла ошибка: {str(e)}")

        finally:
           
            await send_notification("Бот остановлен")

            await client.disconnect()

    asyncio.run(main())
