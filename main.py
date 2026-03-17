import time
import asyncio
import logging
import os  # NEW: For environment variables
from aiogram import Bot, Dispatcher, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.command import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from db import init_db # Add this to your imports
# Import your database functions
from db import (get_categories, get_levels, get_lessons,
                get_lesson_details, set_user_lockout,
                get_user_lockout, get_channels, add_category,
                add_level, add_lesson, update_lesson_content,
                save_unlocked_lesson, is_lesson_unlocked,
                get_user_unlocked_lessons, delete_category,
                add_user, get_all_users, get_stats,
                get_all_lessons_extended, delete_multiple_lessons,
                get_referral_count, get_user_rewards, use_free_pass, add_free_passes)

# --- SECURITY CONFIGURATION ---
try:
    from config import BOT_TOKEN, ADMIN_IDS
except ImportError:
    # If config.py is missing (on the server), set placeholders
    BOT_TOKEN = None
    ADMIN_IDS = []

# This looks for 'BOT_TOKEN' in the server settings. If not found, uses config.py
TOKEN = os.getenv("BOT_TOKEN", BOT_TOKEN)

# This handles Admin IDs. On server, it should be a string like "12345,67890"
env_admins = os.getenv("ADMIN_IDS")
if env_admins:
    ADMINS = [int(id.strip()) for id in env_admins.split(",")]
else:
    ADMINS = ADMIN_IDS
# ------------------------------

# 1. Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[
        logging.FileHandler("bot_log.txt"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# --- 2. FSM STATES ---

class LessonStates(StatesGroup):
    waiting_for_code = State()


class UserStates(StatesGroup):
    waiting_for_feedback = State()


class AdminStates(StatesGroup):
    waiting_for_cat_name = State()
    waiting_for_lvl_name = State()
    waiting_for_lsn_name = State()
    waiting_for_lsn_code = State()
    waiting_for_lsn_content = State()
    waiting_for_broadcast = State()
    selecting_delete = State()
    waiting_for_pass_user_id = State()
    waiting_for_pass_amount = State()


# 3. Initialize Bot
bot = Bot(token=TOKEN)  # Updated to use secure TOKEN
dp = Dispatcher()


# --- 4. KEYBOARDS ---

def main_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="📚 All Materials", callback_data="all_materials"))
    builder.row(types.InlineKeyboardButton(text="📖 My Lessons", callback_data="my_lessons"))
    builder.row(types.InlineKeyboardButton(text="👥 Invite Friends", callback_data="invite"))
    builder.row(types.InlineKeyboardButton(text="✍️ Feedback / Support", callback_data="feedback"))
    return builder.as_markup()


def admin_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="➕ Add Category", callback_data="admin_add_cat"))
    builder.row(types.InlineKeyboardButton(text="📊 Add Level", callback_data="admin_add_lvl"))
    builder.row(types.InlineKeyboardButton(text="📝 Add Lesson", callback_data="admin_add_lsn"))
    builder.row(types.InlineKeyboardButton(text="🗑 Delete Category", callback_data="admin_del_cat"))
    builder.row(types.InlineKeyboardButton(text="❌ Bulk Delete Lessons", callback_data="admin_del_lsn"))
    builder.row(types.InlineKeyboardButton(text="📈 Statistics", callback_data="admin_stats"))
    builder.row(types.InlineKeyboardButton(text="📢 Media Broadcast", callback_data="admin_broadcast"))
    builder.row(types.InlineKeyboardButton(text="🎫 Give Free Pass", callback_data="admin_give_pass"))
    builder.row(types.InlineKeyboardButton(text="🏠 User Menu", callback_data="main_menu"))
    return builder.as_markup()


def bulk_delete_keyboard(all_lessons, selected_ids):
    builder = InlineKeyboardBuilder()
    for lsn_id, name, lvl, cat in all_lessons:
        mark = "✅ " if lsn_id in selected_ids else ""
        builder.row(types.InlineKeyboardButton(
            text=f"{mark}{cat} > {lvl} > {name}",
            callback_data=f"toggle_del_{lsn_id}")
        )
    if selected_ids:
        builder.row(types.InlineKeyboardButton(text=f"🗑 DELETE SELECTED ({len(selected_ids)})",
                                               callback_data="confirm_bulk_delete"))
    builder.row(types.InlineKeyboardButton(text="⬅️ Back", callback_data="admin_main"))
    return builder.as_markup()


# --- 5. UTILS & HELPERS ---

async def get_not_joined_channels(bot: Bot, user_id: int):
    channels = get_channels()
    not_joined = []
    for char_id, url in channels:
        try:
            member = await bot.get_chat_member(chat_id=char_id, user_id=user_id)
            if member.status in ["left", "kicked"]:
                not_joined.append((char_id, url))
        except Exception:
            not_joined.append((char_id, url))
    return not_joined


async def send_lesson_content(message: types.Message, content_id: str, content_type: str, caption: str):
    if not content_id:
        return await message.answer(f"✅ {caption}\n(No content uploaded yet)")
    if content_type == "video":
        await message.answer_video(video=content_id, caption=caption)
    elif content_type == "document":
        await message.answer_document(document=content_id, caption=caption)
    elif content_type == "photo":
        await message.answer_photo(photo=content_id, caption=caption)
    elif content_type == "text":
        await message.answer(f"🔗 **{caption}**\n\n{content_id}", parse_mode="Markdown")
    else:
        await message.answer(f"✅ {caption}\n\nContent: {content_id}")


# --- 6. ADMIN HANDLERS ---

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id not in ADMINS: return  # Updated to use secure ADMINS list
    await message.answer("🛠 Admin Panel:", reply_markup=admin_main_keyboard())


@dp.message(Command("reply"))
async def admin_reply(message: types.Message):
    if message.from_user.id not in ADMINS: return
    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            await message.answer("❌ Usage: `/reply USER_ID message`", parse_mode="Markdown")
            return
        target_id, reply_text = parts[1], parts[2]
        await bot.send_message(target_id, f"✉️ **Message from Admin:**\n\n{reply_text}", parse_mode="Markdown")
        await message.answer(f"✅ Reply sent to `{target_id}`")
    except Exception as e:
        await message.answer(f"❌ Error: {e}")


@dp.callback_query(F.data == "admin_main")
async def back_to_admin(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    try:
        await callback.message.edit_text("🛠 Admin Panel:", reply_markup=admin_main_keyboard())
    except TelegramBadRequest:
        pass


# GIVE FREE PASS
@dp.callback_query(F.data == "admin_give_pass")
async def admin_give_pass_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminStates.waiting_for_pass_user_id)
    await callback.message.answer("Step 1: Enter the **User ID** you want to reward:")


@dp.message(AdminStates.waiting_for_pass_user_id)
async def admin_process_pass_id(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Invalid ID. Send numeric ID:")
        return
    await state.update_data(target_user_id=int(message.text))
    await state.set_state(AdminStates.waiting_for_pass_amount)
    await message.answer(f"Step 2: How many passes for `{message.text}`?")


@dp.message(AdminStates.waiting_for_pass_amount)
async def admin_process_pass_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Enter a number:")
        return
    amount = int(message.text)
    data = await state.get_data()
    add_free_passes(data['target_user_id'], amount)
    await message.answer(f"✅ Added {amount} passes to `{data['target_user_id']}`.", reply_markup=admin_main_keyboard())
    try:
        await bot.send_message(data['target_user_id'], f"🎁 Admin gifted you **{amount} Free Pass(es)**!",
                               parse_mode="Markdown")
    except Exception:
        pass
    await state.clear()


# ADD LESSON
@dp.callback_query(F.data == "admin_add_lsn")
async def admin_select_cat_for_lsn(callback: types.CallbackQuery):
    await callback.answer()
    categories = get_categories()
    builder = InlineKeyboardBuilder()
    for cat_id, name in categories:
        builder.row(types.InlineKeyboardButton(text=name, callback_data=f"asclsn_{cat_id}"))
    builder.row(types.InlineKeyboardButton(text="⬅️ Back", callback_data="admin_main"))
    await callback.message.edit_text("Select Category:", reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith("asclsn_"))
async def admin_select_lvl_for_lsn(callback: types.CallbackQuery):
    cat_id = int(callback.data.split("_")[1])
    levels = get_levels(cat_id)
    builder = InlineKeyboardBuilder()
    for lvl_id, name in levels:
        builder.row(types.InlineKeyboardButton(text=name, callback_data=f"asllsn_{lvl_id}"))
    builder.row(types.InlineKeyboardButton(text="⬅️ Back", callback_data="admin_add_lsn"))
    await callback.message.edit_text("Select Level:", reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith("asllsn_"))
async def admin_ask_lsn_name(callback: types.CallbackQuery, state: FSMContext):
    lvl_id = int(callback.data.split("_")[1])
    await state.update_data(lvl_id=lvl_id)
    await state.set_state(AdminStates.waiting_for_lsn_name)
    await callback.message.answer("Step 1: Enter Lesson Name:")


@dp.message(AdminStates.waiting_for_lsn_name)
async def admin_ask_lsn_code(message: types.Message, state: FSMContext):
    await state.update_data(lsn_name=message.text)
    await state.set_state(AdminStates.waiting_for_lsn_code)
    await message.answer(f"Step 2: Enter access code:")


@dp.message(AdminStates.waiting_for_lsn_code)
async def admin_ask_lsn_content(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lsn_id = add_lesson(data['lvl_id'], data['lsn_name'], message.text)
    await state.update_data(lsn_id=lsn_id)
    await state.set_state(AdminStates.waiting_for_lsn_content)
    await message.answer("Step 3: **UPLOAD CONTENT** (Video, File, Photo, or Link):")


@dp.message(AdminStates.waiting_for_lsn_content)
async def admin_save_lsn_content(message: types.Message, state: FSMContext):
    data = await state.get_data()
    content_id, content_type = None, None
    if message.video:
        content_id, content_type = message.video.file_id, "video"
    elif message.document:
        content_id, content_type = message.document.file_id, "document"
    elif message.photo:
        content_id, content_type = message.photo[-1].file_id, "photo"
    elif message.text:
        content_id, content_type = message.text, "text"

    if not content_type:
        return await message.answer("❌ Unsupported format.")

    update_lesson_content(data['lsn_id'], content_id, content_type)
    await state.clear()
    await message.answer(f"✅ Lesson Saved as {content_type.upper()}!", reply_markup=admin_main_keyboard())


# MEDIA BROADCAST
@dp.callback_query(F.data == "admin_broadcast")
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminStates.waiting_for_broadcast)
    await callback.message.answer("Send the message (Text/Photo/Video) for broadcast:")


@dp.message(AdminStates.waiting_for_broadcast)
async def process_smart_broadcast(message: types.Message, state: FSMContext):
    users = get_all_users()
    await message.answer(f"🚀 Broadcast started for {len(users)} users...")
    success, blocked = 0, 0
    for user_id in users:
        try:
            await message.copy_to(chat_id=user_id)
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            blocked += 1
    await state.clear()
    await message.answer(f"✅ Finished!\n👤 Sent: {success}\n🚫 Blocked: {blocked}", reply_markup=admin_main_keyboard())


# STATS & DELETE
@dp.callback_query(F.data == "admin_stats")
async def show_stats(callback: types.CallbackQuery):
    u_count, l_count = get_stats()
    await callback.answer()
    await callback.message.answer(f"📊 **Bot Stats**\n\nTotal Users: {u_count}\nTotal Lessons: {l_count}",
                                  parse_mode="Markdown")


@dp.callback_query(F.data == "admin_del_lsn")
async def admin_bulk_delete_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    lessons = get_all_lessons_extended()
    if not lessons: return await callback.message.answer("No lessons.")
    await state.update_data(selected_ids=[])
    await state.set_state(AdminStates.selecting_delete)
    await callback.message.edit_text("Select lessons to delete:", reply_markup=bulk_delete_keyboard(lessons, []))


@dp.callback_query(AdminStates.selecting_delete, F.data.startswith("toggle_del_"))
async def admin_toggle_delete_item(callback: types.CallbackQuery, state: FSMContext):
    lsn_id = int(callback.data.split("_")[2])
    data = await state.get_data()
    selected_ids = data.get("selected_ids", [])
    if lsn_id in selected_ids:
        selected_ids.remove(lsn_id)
    else:
        selected_ids.append(lsn_id)
    await state.update_data(selected_ids=selected_ids)
    lessons = get_all_lessons_extended()
    await callback.message.edit_reply_markup(reply_markup=bulk_delete_keyboard(lessons, selected_ids))
    await callback.answer()


@dp.callback_query(AdminStates.selecting_delete, F.data == "confirm_bulk_delete")
async def admin_execute_bulk_delete(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_ids = data.get("selected_ids", [])
    delete_multiple_lessons(selected_ids)
    await state.clear()
    await callback.answer("✅ Deleted!", show_alert=True)
    await callback.message.edit_text("🛠 Admin Panel:", reply_markup=admin_main_keyboard())


@dp.callback_query(F.data == "admin_add_cat")
async def start_add_cat(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminStates.waiting_for_cat_name)
    await callback.message.answer("Enter category name:")


@dp.message(AdminStates.waiting_for_cat_name)
async def save_new_cat(message: types.Message, state: FSMContext):
    add_category(message.text)
    await state.clear()
    await message.answer(f"✅ Category added!", reply_markup=admin_main_keyboard())


@dp.callback_query(F.data == "admin_add_lvl")
async def select_cat_for_lvl(callback: types.CallbackQuery):
    await callback.answer()
    cats = get_categories()
    builder = InlineKeyboardBuilder()
    for cid, name in cats:
        builder.row(types.InlineKeyboardButton(text=name, callback_data=f"asclvl_{cid}"))
    builder.row(types.InlineKeyboardButton(text="⬅️ Back", callback_data="admin_main"))
    await callback.message.edit_text("Select Category:", reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith("asclvl_"))
async def ask_lvl_name(callback: types.CallbackQuery, state: FSMContext):
    cat_id = int(callback.data.split("_")[1])
    await state.update_data(cat_id=cat_id)
    await state.set_state(AdminStates.waiting_for_lvl_name)
    await callback.message.answer("Enter Level name:")


@dp.message(AdminStates.waiting_for_lvl_name)
async def save_new_lvl(message: types.Message, state: FSMContext):
    data = await state.get_data()
    add_level(data['cat_id'], message.text)
    await state.clear()
    await message.answer(f"✅ Level added!", reply_markup=admin_main_keyboard())


@dp.callback_query(F.data == "admin_del_cat")
async def admin_select_cat_to_del(callback: types.CallbackQuery):
    await callback.answer()
    cats = get_categories()
    builder = InlineKeyboardBuilder()
    for cid, name in cats:
        builder.row(types.InlineKeyboardButton(text=f"❌ {name}", callback_data=f"asdel_{cid}"))
    builder.row(types.InlineKeyboardButton(text="⬅️ Back", callback_data="admin_main"))
    await callback.message.edit_text("Delete Category:", reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith("asdel_"))
async def admin_confirm_delete(callback: types.CallbackQuery):
    cat_id = int(callback.data.split("_")[1])
    delete_category(cat_id)
    await callback.answer("✅ Deleted!", show_alert=True)
    await callback.message.edit_text("🛠 Admin Panel:", reply_markup=admin_main_keyboard())


# --- 7. USER HANDLERS ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    args = message.text.split()
    referrer = int(args[1]) if len(args) > 1 and args[1].isdigit() and int(args[1]) != user_id else None
    add_user(user_id, referrer)

    lockout = get_user_lockout(user_id)
    if time.time() < lockout:
        await message.answer("⏳ Locked out.")
        return

    missing = await get_not_joined_channels(message.bot, user_id)
    if missing:
        builder = InlineKeyboardBuilder()
        for char_id, url in missing:
            builder.row(types.InlineKeyboardButton(text=f"Join {char_id}", url=url))
        builder.row(types.InlineKeyboardButton(text="✅ Check Again", callback_data="main_menu"))
        await message.answer("👋 Please join our channels to continue:", reply_markup=builder.as_markup())
        return

    await message.answer("Welcome to the Learning Bot! 🎓", reply_markup=main_menu_keyboard())


@dp.callback_query(F.data == "feedback")
async def start_feedback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(UserStates.waiting_for_feedback)
    await callback.message.answer("✍️ Please send your message or screenshot below.")


@dp.message(UserStates.waiting_for_feedback)
async def process_feedback(message: types.Message, state: FSMContext):
    await message.answer("✅ Sent to administrators!")
    await state.clear()
    for admin_id in ADMINS:
        try:
            await message.forward(chat_id=admin_id)
            await bot.send_message(admin_id,
                                   f"📩 **Feedback** from: {message.from_user.full_name}\nID: `{message.from_user.id}`",
                                   parse_mode="Markdown")
        except Exception:
            pass


@dp.callback_query(F.data == "main_menu")
async def back_to_main(callback: types.CallbackQuery):
    missing = await get_not_joined_channels(callback.bot, callback.from_user.id)
    if missing:
        await callback.answer("❌ Join channels first!", show_alert=True)
        return
    await callback.answer()
    try:
        await callback.message.edit_text("Welcome!", reply_markup=main_menu_keyboard())
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data == "all_materials")
async def show_categories(callback: types.CallbackQuery):
    await callback.answer()
    categories = get_categories()
    builder = InlineKeyboardBuilder()
    for cat_id, cat_name in categories:
        builder.row(types.InlineKeyboardButton(text=cat_name, callback_data=f"category_{cat_id}"))
    builder.row(types.InlineKeyboardButton(text="⬅️ Back", callback_data="main_menu"))
    await callback.message.edit_text("Select Category:", reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith("category_"))
async def show_levels_handler(callback: types.CallbackQuery):
    await callback.answer()
    category_id = int(callback.data.split("_")[1])
    levels = get_levels(category_id)
    builder = InlineKeyboardBuilder()
    for lvl_id, lvl_name in levels:
        builder.row(types.InlineKeyboardButton(text=lvl_name, callback_data=f"level_{lvl_id}"))
    builder.row(types.InlineKeyboardButton(text="⬅️ Back", callback_data="all_materials"))
    await callback.message.edit_text("Select Level:", reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith("level_"))
async def show_lessons_handler(callback: types.CallbackQuery):
    await callback.answer()
    level_id = int(callback.data.split("_")[1])
    lessons = get_lessons(level_id)
    builder = InlineKeyboardBuilder()
    for lsn_id, lsn_name in lessons:
        builder.row(types.InlineKeyboardButton(text=lsn_name, callback_data=f"lesson_{lsn_id}"))
    builder.row(types.InlineKeyboardButton(text="⬅️ Back", callback_data="all_materials"))
    await callback.message.edit_text("Choose Lesson:", reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith("lesson_"))
async def ask_for_lesson_code(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id

    # SAFETY: Register user if they aren't in the new DB yet
    from db import add_user
    add_user(user_id)

    lesson_id = int(callback.data.split("_")[1])
    details = get_lesson_details(lesson_id)

    # 1. Check Unlocked
    if is_lesson_unlocked(user_id, lesson_id):
        await callback.answer()
        await send_lesson_content(callback.message, details[2], details[3], f"✅ {details[0]}")
        return

    # 2. Check for Free Pass
    from db import get_user_rewards
    # Now this will return (0, 0) instead of None, so it won't crash!
    _, passes = get_user_rewards(user_id)

    # ... rest of your code ...

@dp.callback_query(F.data.startswith("use_pass_"))
async def process_use_pass(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    lesson_id = int(callback.data.split("_")[2])
    use_free_pass(user_id)
    save_unlocked_lesson(user_id, lesson_id)
    details = get_lesson_details(lesson_id)
    await callback.answer("🎫 Pass Used!")
    await state.clear()
    await send_lesson_content(callback.message, details[2], details[3], f"✅ Unlocked: {details[0]}")


@dp.message(LessonStates.waiting_for_code)
async def check_code_and_unlock(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if message.text == str(data['correct_code']):
        save_unlocked_lesson(message.from_user.id, data['lesson_id'])
        await send_lesson_content(message, data['content_id'], data['content_type'],
                                  f"✅ Unlocked: {data['lesson_name']}")
        await state.clear()
    else:
        attempts = data.get('attempts', 0) + 1
        if attempts >= 3:
            set_user_lockout(message.from_user.id, 900)
            await message.answer("❌ Locked for 15m.")
            await state.clear()
        else:
            await state.update_data(attempts=attempts)
            await message.answer(f"❌ Wrong. {3 - attempts} left.")


@dp.callback_query(F.data == "my_lessons")
async def show_my_lessons(callback: types.CallbackQuery):
    await callback.answer()
    unlocked = get_user_unlocked_lessons(callback.from_user.id)
    if not unlocked:
        await callback.message.edit_text("No unlocked lessons.", reply_markup=main_menu_keyboard())
        return
    builder = InlineKeyboardBuilder()
    for lsn_id, name in unlocked:
        builder.row(types.InlineKeyboardButton(text=f"✅ {name}", callback_data=f"lesson_{lsn_id}"))
    builder.row(types.InlineKeyboardButton(text="🏠 Menu", callback_data="main_menu"))
    await callback.message.edit_text("Your Lessons:", reply_markup=builder.as_markup())


@dp.callback_query(F.data == "invite")
async def cmd_invite(callback: types.CallbackQuery):
    total_invited = get_referral_count(callback.from_user.id)
    current_progress, passes = get_user_rewards(callback.from_user.id)
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={callback.from_user.id}"
    msg = f"👥 **Referral Program**\nInvited: {total_invited}\nProgress: {current_progress}/5\nPasses: 🎫 **{passes}**\nLink: `{link}`"
    try:
        await callback.message.edit_text(msg, parse_mode="Markdown", reply_markup=main_menu_keyboard())
    except TelegramBadRequest:
        pass


@dp.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Canceled.", reply_markup=main_menu_keyboard())


async def set_commands(bot: Bot):
    commands = [
        types.BotCommand(command="start", description="🚀 Start"),
        types.BotCommand(command="admin", description="🛠 Admin"),
        types.BotCommand(command="cancel", description="❌ Cancel"),
    ]
    await bot.set_my_commands(commands)


async def main():
    # NEW: Build the database tables automatically on the server
    init_db()

    # Set the blue menu button commands
    await set_commands(bot)

    print("Bot is starting...")
    await dp.start_polling(bot)
if __name__ == "__main__":
    asyncio.run(main())