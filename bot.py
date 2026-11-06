import os
from dotenv import load_dotenv
import sqlite3
from pathlib import Path
import logging
from datetime import datetime, time, timedelta, timezone

from telegram import (
    Update, ReplyKeyboardMarkup,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6968440398
DB_NAME = os.path.join(os.getenv("MEDSTUDY_DATA_DIR", "."), "medstudy.db")

logging.basicConfig(level=logging.WARNING)


def db():
    return sqlite3.connect(DB_NAME)


def init_db():
    with db() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(subject_id, name)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                file_id TEXT NOT NULL,
                file_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


        c.execute("""
            CREATE TABLE IF NOT EXISTS teachers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL UNIQUE,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS teacher_profiles (
                telegram_id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                position TEXT NOT NULL,
                academic_degree TEXT DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS access_requests (
                telegram_id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                username TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS daily_reminders (
                reminder_date TEXT PRIMARY KEY,
                schedule_text TEXT NOT NULL DEFAULT '',
                homework_text TEXT NOT NULL DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


        c.execute("""
            CREATE TABLE IF NOT EXISTS custom_section_nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                root_section_id INTEGER NOT NULL,
                parent_id INTEGER,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                position INTEGER NOT NULL DEFAULT 0,
                is_visible INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS custom_section_materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                root_section_id INTEGER NOT NULL,
                node_id INTEGER,
                material_type TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                text_content TEXT NOT NULL DEFAULT '',
                file_id TEXT,
                file_name TEXT,
                mime_type TEXT,
                position INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS homework_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                subject_name TEXT NOT NULL DEFAULT '',
                due_date TEXT NOT NULL DEFAULT '',
                created_by INTEGER,
                is_visible INTEGER NOT NULL DEFAULT 1,
                position INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_section_nodes_parent
            ON custom_section_nodes(root_section_id, parent_id, position)
        """)

        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_section_materials_node
            ON custom_section_materials(root_section_id, node_id, position)
        """)


def subjects():
    with db() as c:
        return c.execute(
            "SELECT id,name FROM subjects ORDER BY id"
        ).fetchall()


def subject(sid):
    with db() as c:
        return c.execute(
            "SELECT id,name FROM subjects WHERE id=?", (sid,)
        ).fetchone()


def topics(sid):
    with db() as c:
        return c.execute(
            "SELECT id,name FROM topics WHERE subject_id=? ORDER BY id",
            (sid,)
        ).fetchall()


def topic(tid):
    with db() as c:
        return c.execute(
            "SELECT id,subject_id,name FROM topics WHERE id=?", (tid,)
        ).fetchone()


def materials(tid):
    with db() as c:
        return c.execute(
            "SELECT id,title,file_id,file_name FROM materials "
            "WHERE topic_id=? ORDER BY id", (tid,)
        ).fetchall()


def has_access(user_id):
    """Foydalanuvchining platformaga kirish huquqini tekshiradi."""
    if user_id == ADMIN_ID:
        return True

    with db() as c:
        teacher = c.execute(
            "SELECT 1 FROM teachers WHERE telegram_id = ?", (user_id,)
        ).fetchone() is not None

        student = c.execute(
            "SELECT 1 FROM students WHERE telegram_id = ?", (user_id,)
        ).fetchone() is not None

        approved = c.execute(
            "SELECT 1 FROM access_requests "
            "WHERE telegram_id = ? AND status = 'approved'",
            (user_id,)
        ).fetchone() is not None

    return teacher or student or approved



def has_teacher_role(user_id):
    with db() as c:
        return c.execute(
            "SELECT 1 FROM teachers WHERE telegram_id = ?",
            (user_id,)
        ).fetchone() is not None



def has_student_role(user_id):
    with db() as c:
        return c.execute(
            "SELECT 1 FROM students WHERE telegram_id = ?",
            (user_id,)
        ).fetchone() is not None



def teacher_profile_text(user_id):
    with db() as c:
        profile = c.execute(
            "SELECT full_name, position, academic_degree "
            "FROM teacher_profiles WHERE telegram_id=?",
            (user_id,)
        ).fetchone()

        subjects = c.execute(
            "SELECT s.name FROM subjects s "
            "JOIN teacher_subjects ts ON ts.subject_id=s.id "
            "WHERE ts.teacher_id=? ORDER BY s.name",
            (user_id,)
        ).fetchall()

    if not profile:
        return (
            "👨‍🏫 USTOZ PROFILI\\n\\n"
            "Profilingiz hali to‘ldirilmagan.\\n"
            "To‘ldirish uchun /editprofile buyrug‘ini yuboring."
        )

    full_name, position, degree = profile
    subject_names = ", ".join(row[0] for row in subjects) or "Hozircha biriktirilmagan"

    return (
        "👨‍🏫 USTOZ PROFILI\\n\\n"
        f"👤 Ism-familiya: {full_name}\\n"
        f"💼 Lavozim: {position}\\n"
        f"🎓 Ilmiy daraja: {degree or 'Kiritilmagan'}\\n"
        f"📚 Biriktirilgan fanlar: {subject_names}\\n"
        f"🆔 Telegram ID: {user_id}\\n\\n"
        "Profilni tahrirlash uchun /editprofile buyrug‘ini yuboring."
    )


def main_menu(admin=False, teacher=False, student=False):
    rows = []

    def btn(label, action):
        return InlineKeyboardButton(label, callback_data=f"nav:{action}")

    if admin:
        rows.append([
            btn("➕ Fan qo‘shish", "add_subject"),
            btn("📖 Mavzu qo‘shish", "add_topic")
        ])
        rows.append([
            btn("📄 PDF qo‘shish", "add_pdf"),
            btn("🛠 Admin panel", "admin_panel")
        ])
        rows.append([btn("📦 Bo‘limlarni boshqarish", "sections")])
        rows.append([btn("👨‍🏫 Ustozlarni boshqarish", "teachers")])
        rows.append([btn("🚫 Foydalanuvchilarni boshqarish", "users")])
    if teacher:
        rows.append([btn("👨‍🏫 Ustoz paneli", "teacher_panel")])

    if student or teacher or admin:
        rows.append([btn("📚 Fanlar", "subjects")])

    with db() as c:
        if admin:
            sections = c.execute(
                "SELECT id, name FROM custom_sections "
                "WHERE is_visible = 1 ORDER BY position, id"
            ).fetchall()
        elif teacher:
            sections = c.execute(
                "SELECT id, name FROM custom_sections "
                "WHERE is_visible = 1 AND show_teachers = 1 "
                "ORDER BY position, id"
            ).fetchall()
        else:
            sections = c.execute(
                "SELECT id, name FROM custom_sections "
                "WHERE is_visible = 1 AND show_students = 1 "
                "ORDER BY position, id"
            ).fetchall()

    for section_id, name in sections:
        label = name if len(name) <= 28 else name[:27] + "…"
        rows.append([
            InlineKeyboardButton(
                "📦 " + label,
                callback_data=f"nav:section:{section_id}"
            )
        ])

    rows.append([
        btn("👤 Profil", "profile"),
        btn("ℹ️ Bot haqida", "about")
    ])

    return InlineKeyboardMarkup(rows)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    user = update.effective_user
    user_id = user.id
    admin = user_id == ADMIN_ID

    with db() as c:
        teacher = c.execute(
            "SELECT 1 FROM teachers WHERE telegram_id = ?",
            (user_id,)
        ).fetchone() is not None

        tables = c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {row[0] for row in tables}

        student = False
        if "students" in table_names:
            student = c.execute(
                "SELECT 1 FROM students WHERE telegram_id = ?",
                (user_id,)
            ).fetchone() is not None

        approved = False
        if "access_requests" in table_names:
            approved = c.execute(
                "SELECT 1 FROM access_requests "
                "WHERE telegram_id = ? AND status = 'approved'",
                (user_id,)
            ).fetchone() is not None

        if admin or teacher or student or approved:
            pass
        else:
            c.execute(
                "INSERT INTO access_requests "
                "(telegram_id, full_name, username, status) "
                "VALUES (?, ?, ?, 'pending') "
                "ON CONFLICT(telegram_id) DO UPDATE SET "
                "full_name=excluded.full_name, "
                "username=excluded.username "
                "WHERE access_requests.status != 'approved'",
                (user_id, user.full_name, user.username)
            )

    if not (admin or teacher or student or approved):
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "📩 Kirish uchun ruxsat so‘rash",
                callback_data="access_request"
            )
        ]])
        await update.message.reply_text(
            "🔒 MedStudy | UBS\n\n"
            "Platforma yopiq. Kirish uchun administratorga "
            "ruxsat so‘rovi yuboring.\n\n"
            f"🆔 Telegram ID: {user_id}",
            reply_markup=keyboard
        )
        return

    await update.message.reply_text(
        "🦷 MedStudy | UBS\n\n"
        "Assalomu alaykum!\n"
        "O‘quv platformasiga xush kelibsiz.",
        reply_markup=main_menu(admin, teacher and not admin, student)
    )

async def show_subjects(message, prefix="subject", user_id=None):
    current_user_id = user_id if user_id is not None else message.from_user.id
    admin = current_user_id == ADMIN_ID
    items = subjects()

    if not admin:
        with db() as c:
            is_teacher = c.execute(
                "SELECT 1 FROM teachers WHERE telegram_id=?",
                (current_user_id,)
            ).fetchone()

            if is_teacher:
                items = c.execute(
                    "SELECT s.id, s.name FROM subjects s "
                    "JOIN teacher_subjects ts ON ts.subject_id=s.id "
                    "WHERE ts.teacher_id=? ORDER BY s.id",
                    (current_user_id,)
                ).fetchall()

    buttons = []
    if not items:
        with db() as c:
            is_teacher = c.execute(
                "SELECT 1 FROM teachers WHERE telegram_id=?",
                (current_user_id,)
            ).fetchone()

        text = (
            "Sizga hali fan biriktirilmagan."
            if is_teacher and not admin
            else "Hozircha fanlar qo‘shilmagan."
        )
    else:
        text = "📚 Kerakli fanni tanlang:"
        with db() as c:
            for sid, name in items:
                topic_count = c.execute(
                    "SELECT COUNT(*) FROM topics WHERE subject_id=?", (sid,)
                ).fetchone()[0]
                pdf_count = c.execute(
                    "SELECT COUNT(*) FROM materials WHERE topic_id IN "
                    "(SELECT id FROM topics WHERE subject_id=?)", (sid,)
                ).fetchone()[0]

                row = [
                    InlineKeyboardButton(
                        f"📚 {name} | {topic_count} mavzu · {pdf_count} fayl" if admin else f"📚 {name}",
                        callback_data=f"{prefix}:{sid}"
                    )
                ]
                if admin and prefix == "subject":
                    row.extend([
                        InlineKeyboardButton("✏️", callback_data=f"renamesubject:{sid}"),
                        InlineKeyboardButton("🗑", callback_data=f"deletesubject:{sid}")
                    ])
                buttons.append(row)

    buttons.append([
        InlineKeyboardButton("🏠 Asosiy menyu", callback_data="nav:home")
    ])

    if hasattr(message, "edit_message_text"):
        await message.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    else:
        await message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

async def show_topics(query, sid, pdf_mode=False, page=0):
    s = subject(sid)
    if not s:
        await query.edit_message_text("Fan topilmadi.")
        return

    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        with db() as c:
            is_teacher = c.execute(
                "SELECT 1 FROM teachers WHERE telegram_id=?",
                (user_id,)
            ).fetchone() is not None

            if is_teacher:
                assigned = c.execute(
                    "SELECT 1 FROM teacher_subjects "
                    "WHERE teacher_id=? AND subject_id=?",
                    (user_id, sid)
                ).fetchone() is not None

                if not assigned:
                    await query.answer(
                        "⛔ Bu fan sizga biriktirilmagan.",
                        show_alert=True
                    )
                    return

    items = topics(sid)
    per_page = 10
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))

    page_items = items[page * per_page:(page + 1) * per_page]
    buttons = []
    row = []

    for tid, name in page_items:
        short_name = name.strip()
        if len(short_name) > 20:
            short_name = short_name[:19] + "…"

        action = "pdf_topic" if pdf_mode else "topic"
        row.append(InlineKeyboardButton(
            short_name,
            callback_data=f"{action}:{tid}"
        ))

        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(
                "⬅️ Oldingi",
                callback_data=f"topicpage:{sid}:{page - 1}:{int(pdf_mode)}"
            ))

        nav.append(InlineKeyboardButton(
            f"📄 {page + 1}/{total_pages}",
            callback_data="topicpage:noop"
        ))

        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(
                "Keyingi ➡️",
                callback_data=f"topicpage:{sid}:{page + 1}:{int(pdf_mode)}"
            ))

        buttons.append(nav)

    if query.from_user.id == ADMIN_ID and not pdf_mode:
        buttons.append([
            InlineKeyboardButton(
                "➕ Shu fanga mavzu qo'shish",
                callback_data=f"addtopic:{sid}"
            )
        ])
        buttons.append([
            InlineKeyboardButton(
                "📚 KTP mavzularini kiritish",
                callback_data=f"addtopics:{sid}"
            )
        ])

    buttons.append([
        InlineKeyboardButton("⬅️ Fanlar", callback_data="all_subjects")
    ])
    buttons.append([
        InlineKeyboardButton("🏠 Asosiy menyu", callback_data="nav:home")
    ])

    if not items:
        title = f"📚 {s[1]}\n\nBu fanga hali mavzu qo'shilmagan."
    elif pdf_mode:
        title = (
            f"📚 {s[1]}\n"
            f"PDF joylashtirish uchun mavzuni tanlang.\n"
            f"📄 Sahifa: {page + 1}/{total_pages}"
        )
    else:
        title = (
            f"📚 {s[1]}\n"
            f"📖 Mavzuni tanlang.\n"
            f"📊 Jami: {len(items)} ta mavzu"
            f"\n📄 Sahifa: {page + 1}/{total_pages}"
        )

    await query.edit_message_text(
        title,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def show_topic(query, tid):
    t = topic(tid)
    if not t:
        await query.edit_message_text("Mavzu topilmadi.")
        return

    user_id = query.from_user.id
    admin_user = user_id == ADMIN_ID
    teacher_user = has_teacher_role(user_id)
    student_user = has_student_role(user_id)

    if not admin_user and not teacher_user and not student_user:
        await query.answer("⛔ Ruxsat yo‘q.", show_alert=True)
        return

    if teacher_user and not admin_user:
        with db() as c:
            assigned = c.execute(
                "SELECT 1 FROM teacher_subjects WHERE teacher_id=? AND subject_id=?",
                (user_id, t[1])
            ).fetchone() is not None

        if not assigned:
            await query.answer(
                "⛔ Bu mavzu sizga biriktirilmagan fan ichida.",
                show_alert=True
            )
            return

    with db() as c:
        materials = c.execute(
            "SELECT id, title, material_type FROM materials "
            "WHERE topic_id=? ORDER BY id",
            (tid,)
        ).fetchall()

        counts = dict(c.execute(
            "SELECT material_type, COUNT(*) FROM materials "
            "WHERE topic_id=? GROUP BY material_type",
            (tid,)
        ).fetchall())

    buttons = []

    if admin_user:
        buttons.extend([
            [InlineKeyboardButton(
                f"📊 Prezentatsiya ({counts.get('presentation', 0)})",
                callback_data=f"topicsection:presentation:{tid}"
            )],
            [InlineKeyboardButton(
                f"📝 Mustaqil ish ({counts.get('independent', 0)})",
                callback_data=f"topicsection:independent:{tid}"
            )],
            [InlineKeyboardButton(
                f"📚 Talabalar uchun materiallar ({counts.get('student_topic', 0)})",
                callback_data=f"topicsection:student_topic:{tid}"
            )],
            [InlineKeyboardButton(
                "✏️ Mavzu nomini o‘zgartirish",
                callback_data=f"renametopic:{tid}"
            )],
            [InlineKeyboardButton(
                "🗑 Mavzuni o‘chirish",
                callback_data=f"deletetopic:{tid}"
            )]
        ])

    elif teacher_user:
        buttons.extend([
            [InlineKeyboardButton(
                f"📊 Prezentatsiyalar ({counts.get('presentation', 0)})",
                callback_data=f"topicsection:presentation:{tid}"
            )],
            [InlineKeyboardButton(
                f"📝 Mustaqil ish ({counts.get('independent', 0)})",
                callback_data=f"topicsection:independent:{tid}"
            )]
        ])

    else:
        student_materials = [
            item for item in materials if item[2] == "student_topic"
        ]

        for mid, title, material_type in student_materials:
            buttons.append([
                InlineKeyboardButton(
                    f"📄 {title}",
                    callback_data=f"material:{mid}"
                )
            ])

    buttons.append([
        InlineKeyboardButton(
            "⬅️ Mavzular",
            callback_data=f"subject:{t[1]}"
        )
    ])

    if admin_user:
        text = f"📖 {t[2]}\n\nKerakli bo‘limni tanlang."
    elif teacher_user:
        text = f"📖 {t[2]}\n\nUstoz materiallari (ko‘rish uchun):"
    else:
        text = f"📖 {t[2]}\n\n"
        text += (
            f"Talabalar uchun materiallar: {len(student_materials)} ta"
            if student_materials else
            "Hozircha bu mavzuga material yuklanmagan."
        )

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    admin = q.from_user.id == ADMIN_ID
    user = q.from_user
    user_id = user.id

    # YANGI UY VAZIFALARI TIZIMI
    if data.startswith("hw:"):
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ""

        if action == "view" and len(parts) == 3 and parts[2].isdigit():
            hw_id = int(parts[2])
            with db() as c:
                if admin:
                    hw = c.execute(
                        "SELECT title, content, subject_name, due_date "
                        "FROM homework_posts WHERE id=?",
                        (hw_id,)
                    ).fetchone()
                else:
                    hw = c.execute(
                        "SELECT title, content, subject_name, due_date "
                        "FROM homework_posts WHERE id=? AND is_visible=1",
                        (hw_id,)
                    ).fetchone()

            if not hw:
                await q.answer("Vazifa topilmadi yoki yashirilgan.", show_alert=True)
                return

            title, content, hw_subject_name, due_date = hw
            await q.edit_message_text(
                f"📝 {title}\\n\\n"
                f"📚 Fan: {hw_subject_name}\\n"
                f"📅 Muddat: {due_date or 'Belgilanmagan'}\\n\\n"
                f"📄 Vazifa matni:\\n{content}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "⬅️ Uy vazifalariga qaytish",
                        callback_data="nav:section:7"
                    )
                ]])
            )
            return

        if not admin:
            await q.answer("⛔ Bu amal faqat administrator uchun.", show_alert=True)
            return

        if action == "add":
            context.user_data.clear()
            context.user_data["waiting_hw_title"] = True
            await q.message.reply_text(
                "📝 Yangi vazifa nomini yuboring.\n\n"
                "Masalan: Bosh miya nervlari — mustaqil ish"
            )
            return

        if action == "subject" and len(parts) == 3:
            subject_id = parts[2]
            if subject_id == "general":
                subject_name = "Umumiy"
            else:
                if not subject_id.isdigit():
                    await q.answer("Fan tanlashda xatolik.", show_alert=True)
                    return
                with db() as c:
                    row = c.execute(
                        "SELECT name FROM subjects WHERE id = ?",
                        (int(subject_id),)
                    ).fetchone()
                if not row:
                    await q.answer("Fan topilmadi.", show_alert=True)
                    return
                subject_name = row[0]

            context.user_data["hw_subject"] = subject_name
            context.user_data.pop("waiting_hw_subject", None)
            context.user_data["waiting_hw_content"] = True
            await q.message.reply_text(
                f"📚 Fan: {subject_name}\n\n"
                "Endi uy vazifasining batafsil matnini yuboring. "
                "Maksimal 3500 belgi."
            )
            return

        if action == "nodue":
            title = context.user_data.get("hw_title")
            hw_subject_name = context.user_data.get("hw_subject")
            content = context.user_data.get("hw_content")

            if not title or not hw_subject_name or not content:
                context.user_data.clear()
                await q.message.reply_text("Ma’lumotlar yetishmayapti. Qaytadan boshlang.")
                return

            with db() as c:
                c.execute(
                    """INSERT INTO homework_posts
                       (title, content, subject_name, due_date, created_by)
                       VALUES (?, ?, ?, '', ?)""",
                    (title, content, hw_subject_name, user_id)
                )

            context.user_data.clear()
            await q.message.reply_text(
                "✅ UY VAZIFASI SAQLANDI!\n\n"
                f"📝 {title}\n"
                f"📚 Fan: {hw_subject_name}\n"
                "📅 Muddat: belgilanmagan",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ Yana vazifa qo‘shish", callback_data="hw:add")],
                    [InlineKeyboardButton("📋 Vazifalar ro‘yxati", callback_data="hw:list")],
                    [InlineKeyboardButton("🏠 Asosiy menyu", callback_data="nav:home")]
                ])
            )
            return

        if action == "manage" and len(parts) == 3 and parts[2].isdigit():
            hw_id = int(parts[2])
            with db() as c:
                hw = c.execute(
                    "SELECT title, content, subject_name, due_date, is_visible "
                    "FROM homework_posts WHERE id=?",
                    (hw_id,)
                ).fetchone()

            if not hw:
                await q.message.reply_text("Vazifa topilmadi.")
                return

            title, content, hw_subject_name, due_date, visible = hw
            await q.edit_message_text(
                f"📝 {title}\\n\\n"
                f"📚 Fan: {hw_subject_name}\\n"
                f"📅 Muddat: {due_date or 'Belgilanmagan'}\\n"
                f"👁 Holati: {'Ko‘rinadi' if visible else 'Yashirilgan'}\\n\\n"
                f"📄 Vazifa matni:\\n{content}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("👁 Ko‘rinishini almashtirish", callback_data=f"hw:toggle:{hw_id}")],
                    [InlineKeyboardButton("🗑 O‘chirish", callback_data=f"hw:delete:{hw_id}")],
                    [InlineKeyboardButton("⬅️ Vazifalar ro‘yxati", callback_data="hw:list")]
                ])
            )
            return

        if action == "toggle" and len(parts) == 3 and parts[2].isdigit():
            hw_id = int(parts[2])
            with db() as c:
                c.execute(
                    "UPDATE homework_posts SET is_visible = CASE WHEN is_visible=1 THEN 0 ELSE 1 END, "
                    "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (hw_id,)
                )
            await q.message.reply_text(
                "✅ Vazifaning ko‘rinish holati o‘zgartirildi.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📋 Vazifani ochish", callback_data=f"hw:manage:{hw_id}")
                ]])
            )
            return

        if action == "delete" and len(parts) == 3 and parts[2].isdigit():
            hw_id = int(parts[2])
            await q.edit_message_text(
                "⚠️ Ushbu uy vazifasini o‘chirishni tasdiqlaysizmi?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Ha, o‘chirilsin", callback_data=f"hw:deleteconfirm:{hw_id}")],
                    [InlineKeyboardButton("❌ Bekor qilish", callback_data=f"hw:manage:{hw_id}")]
                ])
            )
            return

        if action == "deleteconfirm" and len(parts) == 3 and parts[2].isdigit():
            hw_id = int(parts[2])
            with db() as c:
                c.execute("DELETE FROM homework_posts WHERE id=?", (hw_id,))
            await q.edit_message_text(
                "🗑 Uy vazifasi o‘chirildi.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📋 Vazifalar ro‘yxati", callback_data="hw:list")
                ]])
            )
            return

        if action == "list":
            with db() as c:
                rows = c.execute(
                    "SELECT id, title, subject_name, due_date "
                    "FROM homework_posts ORDER BY position, id DESC"
                ).fetchall()

            if not rows:
                await q.message.reply_text(
                    "Hozircha uy vazifalari kiritilmagan.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("⬅️ Orqaga", callback_data="nav:homework")
                    ]])
                )
                return

            buttons = []
            for hw_id, title, hw_subject_name, due_date in rows:
                buttons.append([InlineKeyboardButton(
                    f"📝 {title[:45]}",
                    callback_data=f"hw:manage:{hw_id}"
                )])

            buttons.append([InlineKeyboardButton(
                "⬅️ Orqaga", callback_data="nav:homework"
            )])

            await q.message.reply_text(
                "📋 SAQLANGAN UY VAZIFALARI",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return

        await q.answer("Bu amal hali mavjud emas.")
        return

    # Jadval va uy vazifalarini boshqarish
    if data.startswith("reminder:"):
        if not admin:
            await q.message.reply_text("⛔ Faqat administrator uchun.")
            return

        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ""
        kind = parts[2] if len(parts) > 2 else ""
        if kind not in ("schedule_text", "homework_text"):
            await q.message.reply_text("Noto‘g‘ri bo‘lim.")
            return

        label = "📅 Dars jadvali" if kind == "schedule_text" else "📝 Uy vazifasi"
        column = "schedule_text" if kind == "schedule_text" else "homework_text"

        if action == "add":
            context.user_data.clear()
            context.user_data["waiting_reminder_date"] = kind
            await q.message.reply_text(
                f"{label} sanasini YYYY-MM-DD formatida yuboring. Bekor qilish: /cancel"
            )
            return

        if action == "list":
            with db() as c:
                rows = c.execute(
                    f"SELECT reminder_date, {column} FROM daily_reminders "
                    f"WHERE TRIM({column}) != '' ORDER BY reminder_date"
                ).fetchall()
            if not rows:
                await q.message.reply_text("Bu bo‘limda saqlangan ma’lumot yo‘q.")
                return
            buttons = []
            for date_value, content in rows:
                preview = content.replace("\n", " ")[:35]
                buttons.append([InlineKeyboardButton(
                    f"📅 {date_value} — {preview}",
                    callback_data=f"reminder:show:{kind}:{date_value}"
                )])
            await q.message.reply_text(
                f"{label} — saqlangan sanalar:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return

        if action == "show" and len(parts) == 4:
            date_value = parts[3]
            with db() as c:
                row = c.execute(
                    f"SELECT {column} FROM daily_reminders WHERE reminder_date = ?",
                    (date_value,)
                ).fetchone()
            if not row or not row[0].strip():
                await q.message.reply_text("Bu sana uchun ma’lumot topilmadi.")
                return
            buttons = [[
                InlineKeyboardButton("✏️ Tahrirlash", callback_data=f"reminder:edit:{kind}:{date_value}"),
                InlineKeyboardButton("🗑 O‘chirish", callback_data=f"reminder:delete:{kind}:{date_value}")
            ]]
            await q.message.reply_text(
                f"{label} — {date_value}\n\n{row[0]}",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return

        if action == "edit" and len(parts) == 4:
            context.user_data.clear()
            context.user_data["waiting_reminder_content"] = kind
            context.user_data["reminder_date"] = parts[3]
            await q.message.reply_text(
                f"{parts[3]} sanasi uchun yangi matnni yuboring. "
                "Faqat shu bo‘lim yangilanadi. Bekor qilish: /cancel"
            )
            return

        if action == "delete" and len(parts) == 4:
            date_value = parts[3]
            await q.message.reply_text(
                f"⚠️ {date_value} sanasidagi {label}ni o‘chirishni tasdiqlaysizmi?",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "✅ Ha, o‘chir",
                        callback_data=f"reminder:confirmdelete:{kind}:{date_value}"
                    ),
                    InlineKeyboardButton(
                        "❌ Bekor qilish",
                        callback_data=f"reminder:show:{kind}:{date_value}"
                    )
                ]])
            )
            return

        if action == "confirmdelete" and len(parts) == 4:
            date_value = parts[3]
            with db() as c:
                c.execute(
                    f"UPDATE daily_reminders SET {column} = '', "
                    "updated_at = CURRENT_TIMESTAMP WHERE reminder_date = ?",
                    (date_value,)
                )
            await q.message.reply_text(
                f"🗑 {date_value} sanasidagi {label} o‘chirildi.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "📋 Saqlangan sanalar",
                        callback_data=f"reminder:list:{kind}"
                    )
                ]])
            )
            return

        await q.message.reply_text("Bu amal tanilmadi.")
        return

    # Kirish uchun ruxsat so‘rovi
    if data == "access_request":
        if has_access(user_id):
            await q.message.reply_text("✅ Sizda kirish uchun ruxsat bor. /start ni bosing.")
            return

        with db() as c:
            c.execute(
                "INSERT INTO access_requests "
                "(telegram_id, full_name, username, status) "
                "VALUES (?, ?, ?, 'pending') "
                "ON CONFLICT(telegram_id) DO UPDATE SET "
                "full_name=excluded.full_name, username=excluded.username "
                "WHERE access_requests.status != 'approved'",
                (user_id, user.full_name, user.username)
            )
            request = c.execute(
                "SELECT status FROM access_requests WHERE telegram_id=?",
                (user_id,)
            ).fetchone()

        if request and request[0] == "approved":
            await q.message.reply_text("✅ Sizga avvaldan ruxsat berilgan. /start ni bosing.")
            return

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Ruxsat berish", callback_data=f"approveaccess:{user_id}"),
            InlineKeyboardButton("❌ Rad etish", callback_data=f"denyaccess:{user_id}")
        ]])

        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    "📩 MedStudy | UBS — yangi kirish so‘rovi\n\n"
                    f"👤 Ism: {user.full_name}\n"
                    f"🔗 Username: @{user.username if user.username else 'yo‘q'}\n"
                    f"🆔 Telegram ID: {user_id}"
                ),
                reply_markup=keyboard
            )
            await q.message.reply_text("📨 So‘rovingiz adminga yuborildi. Javobni kuting.")
        except Exception:
            await q.message.reply_text(
                "⚠️ So‘rov saqlandi, lekin adminga xabar yuborilmadi. "
                "Administrator botni ishga tushirganini tekshiring."
            )
        return

    # Admin so‘rovni tasdiqlashi
    if data.startswith("approveaccess:"):
        if not admin:
            await q.message.reply_text("⛔ Bu amal faqat administrator uchun.")
            return

        target_id = int(data.split(":", 1)[1])
        with db() as c:
            c.execute(
                "UPDATE access_requests SET status='approved' WHERE telegram_id=?",
                (target_id,)
            )
            exists = c.execute(
                "SELECT 1 FROM access_requests WHERE telegram_id=?",
                (target_id,)
            ).fetchone()

        if not exists:
            await q.message.reply_text("⚠️ So‘rov topilmadi.")
            return

        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="✅ Kirish so‘rovingiz tasdiqlandi! MedStudy | UBS uchun /start ni bosing."
            )
        except Exception:
            pass

        await q.message.reply_text(f"✅ {target_id} foydalanuvchiga ruxsat berildi.")
        return

    # Admin so‘rovni rad etishi
    if data.startswith("denyaccess:"):
        if not admin:
            await q.message.reply_text("⛔ Bu amal faqat administrator uchun.")
            return

        target_id = int(data.split(":", 1)[1])
        with db() as c:
            c.execute(
                "UPDATE access_requests SET status='rejected' WHERE telegram_id=?",
                (target_id,)
            )
            exists = c.execute(
                "SELECT 1 FROM access_requests WHERE telegram_id=?",
                (target_id,)
            ).fetchone()

        if not exists:
            await q.message.reply_text("⚠️ So‘rov topilmadi.")
            return

        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="❌ Kirish so‘rovingiz rad etildi. Qo‘shimcha ma’lumot uchun administratorga murojaat qiling."
            )
        except Exception:
            pass

        await q.message.reply_text(f"❌ {target_id} foydalanuvchining so‘rovi rad etildi.")
        return

    # Boshqa barcha tugmalar uchun majburiy ruxsat tekshiruvi
    if not has_access(user_id):
        await q.message.reply_text(
            "🔒 Bu platformadan foydalanish uchun administrator ruxsati kerak. /start ni bosing."
        )
        return


    # YANGI INLINE MENYU NAVIGATSIYASI
    if data.startswith("nav:"):
        action = data[4:]
        if action.startswith("renamenode:"):
            if not admin:
                await q.answer("Faqat administrator uchun.", show_alert=True)
                return

            parts = action.split(":")
            if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
                await q.answer("Papka manzili noto'g'ri.", show_alert=True)
                return

            section_id, node_id = int(parts[1]), int(parts[2])

            with db() as c:
                node = c.execute(
                    "SELECT name FROM custom_section_nodes "
                    "WHERE id=? AND root_section_id=?",
                    (node_id, section_id)
                ).fetchone()

            if not node:
                await q.answer("Papka topilmadi.", show_alert=True)
                return

            context.user_data.clear()
            context.user_data["waiting_custom_node_name"] = True
            context.user_data["custom_node_root_id"] = section_id
            context.user_data["rename_custom_node_id"] = node_id

            await q.answer()
            await q.message.reply_text(
                f"✏️ Hozirgi papka nomi: {node[0]}\\n"
                "Yangi nomini yuboring. Bekor qilish: /cancel"
            )
            return

        if action.startswith("deletenode:"):
            if not admin:
                await q.edit_message_text("⛔ Faqat administrator uchun.")
                return

            parts = action.split(":")
            if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
                await q.edit_message_text("Noto'g'ri papka manzili.")
                return

            section_id, node_id = int(parts[1]), int(parts[2])

            with db() as c:
                node = c.execute(
                    "SELECT name, parent_id FROM custom_section_nodes "
                    "WHERE id=? AND root_section_id=?",
                    (node_id, section_id)
                ).fetchone()

                root = c.execute(
                    "SELECT id FROM custom_sections WHERE id=?",
                    (section_id,)
                ).fetchone()

                if node and root:
                    counts = c.execute("""
                        WITH RECURSIVE subtree(id) AS (
                            SELECT id FROM custom_section_nodes
                            WHERE id=? AND root_section_id=?
                            UNION
                            SELECT n.id
                            FROM custom_section_nodes n
                            JOIN subtree s ON n.parent_id=s.id
                            WHERE n.root_section_id=?
                        )
                        SELECT
                            COUNT(*),
                            (SELECT COUNT(*)
                             FROM custom_section_materials m
                             WHERE m.root_section_id=?
                             AND m.node_id IN (SELECT id FROM subtree))
                        FROM subtree
                    """, (
                        node_id, section_id, section_id, section_id
                    )).fetchone()
                else:
                    counts = None

            if not node or not root:
                await q.edit_message_text("Papka topilmadi.")
                return

            parent_id = node[1]
            back_callback = (
                f"nav:node:{section_id}:{parent_id}"
                if parent_id is not None
                else f"nav:section:{section_id}"
            )

            await q.edit_message_text(
                f"⚠️ PAPKANI O'CHIRISH\n\n"
                f"📂 Nomi: {node[0]}\n"
                f"📁 Ichki papkalar bilan jami: {counts[0]} ta\n"
                f"📎 Materiallar: {counts[1]} ta\n\n"
                f"Ushbu papka va uning barcha ichidagi "
                f"ma'lumotlari o'chiriladi.\n"
                f"Bu amalni ortga qaytarib bo'lmaydi.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "✅ Ha, hammasini o'chir",
                        callback_data=f"nav:confirmdeletenode:{section_id}:{node_id}"
                    )],
                    [InlineKeyboardButton(
                        "❌ Bekor qilish",
                        callback_data=back_callback
                    )]
                ])
            )
            return

        if action.startswith("confirmdeletenode:"):
            if not admin:
                await q.edit_message_text("⛔ Faqat administrator uchun.")
                return

            parts = action.split(":")
            if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
                await q.edit_message_text("Noto'g'ri papka manzili.")
                return

            section_id, node_id = int(parts[1]), int(parts[2])

            try:
                with db() as c:
                    node = c.execute(
                        "SELECT name, parent_id FROM custom_section_nodes "
                        "WHERE id=? AND root_section_id=?",
                        (node_id, section_id)
                    ).fetchone()

                    root = c.execute(
                        "SELECT id FROM custom_sections WHERE id=?",
                        (section_id,)
                    ).fetchone()

                    if not node or not root:
                        await q.edit_message_text(
                            "Papka topilmadi yoki avval o'chirilgan."
                        )
                        return

                    node_name, parent_id = node

                    c.execute("""
                        WITH RECURSIVE subtree(id) AS (
                            SELECT id FROM custom_section_nodes
                            WHERE id=? AND root_section_id=?
                            UNION
                            SELECT n.id
                            FROM custom_section_nodes n
                            JOIN subtree s ON n.parent_id=s.id
                            WHERE n.root_section_id=?
                        )
                        DELETE FROM custom_section_materials
                        WHERE root_section_id=?
                        AND node_id IN (SELECT id FROM subtree)
                    """, (
                        node_id, section_id, section_id, section_id
                    ))

                    c.execute("""
                        WITH RECURSIVE subtree(id) AS (
                            SELECT id FROM custom_section_nodes
                            WHERE id=? AND root_section_id=?
                            UNION
                            SELECT n.id
                            FROM custom_section_nodes n
                            JOIN subtree s ON n.parent_id=s.id
                            WHERE n.root_section_id=?
                        )
                        DELETE FROM custom_section_nodes
                        WHERE root_section_id=?
                        AND id IN (SELECT id FROM subtree)
                    """, (
                        node_id, section_id, section_id, section_id
                    ))

            except sqlite3.Error:
                logging.exception("Ichki papkani o'chirishda xatolik")
                await q.edit_message_text(
                    "❌ O'chirishda xatolik yuz berdi. "
                    "Ma'lumotlar bazasi tranzaksiyasi bekor qilindi."
                )
                return

            back_callback = (
                f"nav:node:{section_id}:{parent_id}"
                if parent_id is not None
                else f"nav:section:{section_id}"
            )

            await q.edit_message_text(
                f"✅ Papka muvaffaqiyatli o'chirildi.\n\n"
                f"📂 {node_name}\n"
                f"Ichki papkalar va materiallar ham o'chirildi.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "⬅️ Orqaga",
                        callback_data=back_callback
                    )
                ]])
            )
            return

        if action == "finishmaterial":
            if not admin:
                await q.answer("Faqat administrator uchun.", show_alert=True)
                return

            if not context.user_data.get("waiting_custom_material_files"):
                await q.answer("Faol yuklash jarayoni topilmadi.", show_alert=True)
                return

            count = context.user_data.get("custom_material_count", 0)
            if count == 0:
                await q.answer("Hali hech qanday fayl yuborilmadi.", show_alert=True)
                return

            for key in (
                "waiting_custom_material_files",
                "custom_material_root_id",
                "custom_material_node_id",
                "custom_material_title",
                "custom_material_description",
                "custom_material_count",
            ):
                context.user_data.pop(key, None)

            await q.answer("Yuklash yakunlandi!")
            await q.edit_message_text(
                f"✅ Materiallar muvaffaqiyatli saqlandi.\\n"
                f"📎 Jami fayllar: {count}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "🏠 Asosiy menyu",
                        callback_data="nav:home"
                    )
                ]])
            )
            return



        def nav_keyboard(*rows):
            return InlineKeyboardMarkup([
                [InlineKeyboardButton(label, callback_data=callback)
                 for label, callback in row]
                for row in rows
            ])

        home = ("🏠 Asosiy menyu", "nav:home")

        if action in ("add_subject", "add_topic", "add_pdf"):
            if not admin:
                await q.answer("Faqat administrator uchun.", show_alert=True)
                return

            if action == "add_subject":
                context.user_data.clear()
                context.user_data["waiting_subject_name"] = True
                await q.edit_message_text(
                    "➕ YANGI FAN\n\nFan nomini yuboring. Bekor qilish: /cancel",
                    reply_markup=nav_keyboard([home])
                )
                return

            if action == "add_topic":
                await show_subjects(q, "subject")
                return

            if action == "add_pdf":
                await show_subjects(q, "pdf_subject")
                return

        if action == "sections":
            if not admin:
                await q.answer("Faqat administrator uchun.", show_alert=True)
                return

            with db() as c:
                items = c.execute(
                    "SELECT id, name, is_visible, show_students, show_teachers "
                    "FROM custom_sections ORDER BY position, id"
                ).fetchall()

            rows = [
                [InlineKeyboardButton("➕ Bo‘lim qo‘shish", callback_data="nav:add_section")]
            ]

            for sid, name, visible, students, teachers in items:
                rows.append([
                    InlineKeyboardButton(
                        f"📦 {name[:22]}",
                        callback_data=f"nav:section_manage:{sid}"
                    )
                ])

            rows.append([InlineKeyboardButton("🏠 Asosiy menyu", callback_data="nav:home")])
            await q.edit_message_text(
                "📦 BO‘LIMLARNI BOSHQARISH\n\nKerakli bo‘limni tanlang:",
                reply_markup=InlineKeyboardMarkup(rows)
            )
            return

        if action == "add_section":
            if not admin:
                await q.answer("Faqat administrator uchun.", show_alert=True)
                return
            context.user_data.clear()
            await q.edit_message_text(
                "➕ YANGI BO‘LIM\n\nKimlarga ko‘rinishini tanlang:",
                reply_markup=nav_keyboard(
                    [("👨‍🎓 Faqat talabalar", "nav:section_audience:students")],
                    [("👨‍🏫 Faqat o‘qituvchilar", "nav:section_audience:teachers")],
                    [("👥 Talabalar va o‘qituvchilar", "nav:section_audience:both")],
                    [home]
                )
            )
            return

        if action.startswith("section_audience:"):
            if not admin:
                await q.answer("Faqat administrator uchun.", show_alert=True)
                return

            audience = action.split(":", 1)[1]
            choices = {
                "students": (1, 0, "Faqat talabalar"),
                "teachers": (0, 1, "Faqat o‘qituvchilar"),
                "both": (1, 1, "Talabalar va o‘qituvchilar")
            }

            if audience not in choices:
                await q.answer("Noto‘g‘ri tanlov.", show_alert=True)
                return

            show_students, show_teachers, label = choices[audience]
            context.user_data.clear()
            context.user_data["waiting_section_name"] = True
            context.user_data["section_show_students"] = show_students
            context.user_data["section_show_teachers"] = show_teachers

            await q.edit_message_text(
                f"➕ YANGI BO‘LIM\n\n"
                f"Ko‘rinish: {label}\n\n"
                "Endi bo‘lim nomini yuboring. Bekor qilish: /cancel",
                reply_markup=nav_keyboard([home])
            )
            return

        if action.startswith("section_manage:"):
            if not admin:
                await q.answer("Ruxsat yo‘q.", show_alert=True)
                return
            try:
                sid = int(action.split(":", 1)[1])
            except ValueError:
                await q.answer("Noto‘g‘ri ID.", show_alert=True)
                return

            with db() as c:
                item = c.execute(
                    "SELECT name, is_visible, show_students, show_teachers "
                    "FROM custom_sections WHERE id=?",
                    (sid,)
                ).fetchone()

            if not item:
                await q.answer("Bo‘lim topilmadi.", show_alert=True)
                return

            name, visible, students, teachers = item
            await q.edit_message_text(
                f"📦 {name}\n\n"
                f"Umumiy ko‘rinish: {'Ha' if visible else 'Yo‘q'}\n"
                f"Talabalar: {'Ha' if students else 'Yo‘q'}\n"
                f"Ustozlar: {'Ha' if teachers else 'Yo‘q'}",
                reply_markup=nav_keyboard(
                    [("✏️ Nomini o‘zgartirish", f"renamesection:{sid}")],
                    [("👁 Ko‘rinishni almashtirish", f"togglesection:{sid}")],
                    [(f"👨‍🎓 Talabalar: {'ha' if students else 'yo‘q'}", f"togglestudents:{sid}")],
                    [(f"👨‍🏫 Ustozlar: {'ha' if teachers else 'yo‘q'}", f"toggleteachers:{sid}")],
                    [("🗑 O‘chirish", f"deletesection:{sid}")],
                    [("⬅️ Bo‘limlar ro‘yxati", "nav:sections")]
                )
            )
            return

        if action == "users":
            if not admin:
                await q.answer("Faqat administrator uchun.", show_alert=True)
                return

            with db() as c:
                students = c.execute(
                    "SELECT telegram_id, full_name FROM students"
                ).fetchall()
                teachers = c.execute(
                    "SELECT telegram_id FROM teachers"
                ).fetchall()
                requests = c.execute(
                    "SELECT telegram_id, full_name, status FROM access_requests"
                ).fetchall()

            people = {}

            for row in students:
                people[row[0]] = {
                    "name": row[1] or "Noma’lum",
                    "roles": ["Talaba"]
                }

            for row in teachers:
                tid = row[0]
                if tid not in people:
                    people[tid] = {"name": "Noma’lum", "roles": []}
                people[tid]["roles"].append("Ustoz")

            for row in requests:
                tid, name, status = row
                if tid not in people:
                    people[tid] = {
                        "name": name or "Noma’lum",
                        "roles": []
                    }
                if status == "approved" and not people[tid]["roles"]:
                    people[tid]["roles"].append("Ruxsat berilgan")

            rows = []
            for tid, person in sorted(people.items()):
                roles = " + ".join(person["roles"]) or "So‘rov"
                rows.append([
                    InlineKeyboardButton(
                        f"🚫 {person['name']} | {roles}",
                        callback_data=f"removeuser:{tid}"
                    )
                ])

            rows.append([
                InlineKeyboardButton("🏠 Asosiy menyu", callback_data="nav:home")
            ])

            await q.edit_message_text(
                "🚫 FOYDALANUVCHILARNI BOSHQARISH\\n\\n"
                f"Jami: {len(people)} ta foydalanuvchi\\n"
                "O‘chirish uchun foydalanuvchini tanlang:",
                reply_markup=InlineKeyboardMarkup(rows)
            )
            return

        if action == "teachers":
            if not admin:
                await q.answer("Faqat administrator uchun.", show_alert=True)
                return

            with db() as c:
                teachers = c.execute(
                    "SELECT telegram_id FROM teachers ORDER BY id"
                ).fetchall()

            rows = [
                [InlineKeyboardButton("➕ Ustoz qo‘shish", callback_data="nav:add_teacher")],
                [InlineKeyboardButton("🎓 Fan biriktirish", callback_data="nav:assign_teacher")]
            ]

            for row in teachers:
                tid = row[0]
                rows.append([
                    InlineKeyboardButton(
                        f"👨‍🏫 {tid} — ruxsatni bekor qilish",
                        callback_data=f"removeteacher:{tid}"
                    )
                ])

            rows.append([InlineKeyboardButton("🏠 Asosiy menyu", callback_data="nav:home")])
            await q.edit_message_text(
                "👨‍🏫 USTOZLARNI BOSHQARISH\n\n"
                f"Ro‘yxatdagi ustozlar: {len(teachers)}",
                reply_markup=InlineKeyboardMarkup(rows)
            )
            return

        if action == "add_teacher":
            if not admin:
                await q.answer("Faqat administrator uchun.", show_alert=True)
                return
            context.user_data.clear()
            context.user_data["waiting_teacher_id"] = True
            await q.edit_message_text(
                "➕ USTOZ QO‘SHISH\n\n"
                "Ustozning Telegram ID raqamini yuboring. Bekor qilish: /cancel"
            )
            return

        if action == "assign_teacher":
            if not admin:
                await q.answer("Faqat administrator uchun.", show_alert=True)
                return
            with db() as c:
                teacher_rows = c.execute(
                    "SELECT telegram_id FROM teachers ORDER BY id"
                ).fetchall()

            if not teacher_rows:
                await q.edit_message_text(
                    "Hozircha ustozlar yo‘q. Avval ustoz qo‘shing.",
                    reply_markup=nav_keyboard([home])
                )
                return

            rows = [
                [(f"👨‍🏫 {row[0]}", f"assignteacher:{row[0]}")]
                for row in teacher_rows
            ]
            rows.append([home])
            await q.edit_message_text(
                "Fan biriktirish uchun ustozni tanlang:",
                reply_markup=nav_keyboard(*rows)
            )
            return

        if action == "admin_panel":
            if not admin:
                await q.answer("Faqat administrator uchun.", show_alert=True)
                return
            await q.edit_message_text(
                "🛠 ADMIN PANEL\n\n"
                "MedStudy | UBS boshqaruv markazi.\n"
                "Kerakli amalni asosiy menyudan tanlashingiz mumkin.",
                reply_markup=nav_keyboard(
                    [("➕ Fan qo‘shish", "nav:add_subject")],
                    [("📖 Mavzu qo‘shish", "nav:add_topic")],
                    [("📄 PDF qo‘shish", "nav:add_pdf")],
                    [("📦 Bo‘limlarni boshqarish", "nav:sections")],
                    [("👨‍🏫 Ustozlarni boshqarish", "nav:teachers")],
                    [("🏠 Asosiy menyu", "nav:home")]
                )
            )
            return

        if action == "home":
            with db() as c:
                teacher = c.execute(
                    "SELECT 1 FROM teachers WHERE telegram_id=?",
                    (user_id,)
                ).fetchone() is not None
                student = c.execute(
                    "SELECT 1 FROM students WHERE telegram_id=?",
                    (user_id,)
                ).fetchone() is not None

            await q.edit_message_text(
                "🦷 MedStudy | UBS\n\nAssalomu alaykum!\nO‘quv platformasiga xush kelibsiz.",
                reply_markup=main_menu(admin, teacher and not admin, student)
            )
            return

        if action == "subjects":
            await show_subjects(q)
            return

        if action == "about":
            await q.edit_message_text(
                "🦷 MedStudy | UBS\n\nTalabalar uchun o‘quv platformasi.",
                reply_markup=nav_keyboard([home])
            )
            return

        if action == "profile":
            if has_teacher_role(user_id) and user_id != ADMIN_ID:
                profile_text = teacher_profile_text(user_id)
            else:
                with db() as c:
                    c.execute("""
                        CREATE TABLE IF NOT EXISTS students (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            telegram_id INTEGER UNIQUE NOT NULL,
                            full_name TEXT NOT NULL,
                            group_name TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    c.execute("""
                        CREATE TABLE IF NOT EXISTS student_stats (
                            student_id INTEGER PRIMARY KEY,
                            completed_topics INTEGER NOT NULL DEFAULT 0,
                            tests_completed INTEGER NOT NULL DEFAULT 0,
                            total_score INTEGER NOT NULL DEFAULT 0,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    student = c.execute(
                        "SELECT id, full_name, group_name FROM students WHERE telegram_id=?",
                        (user_id,)
                    ).fetchone()

                    if student:
                        sid, full_name, group_name = student
                        c.execute(
                            "INSERT OR IGNORE INTO student_stats (student_id) VALUES (?)",
                            (sid,)
                        )
                        stats = c.execute(
                            "SELECT completed_topics, tests_completed, total_score "
                            "FROM student_stats WHERE student_id=?",
                            (sid,)
                        ).fetchone()
                        completed, tests, score = stats or (0, 0, 0)
                        profile_text = (
                            "👤 TALABA PROFILI\\n\\n"
                            f"🧑 Ism: {full_name}\\n"
                            f"🎓 Guruh: {group_name or 'Kiritilmagan'}\\n"
                            f"🆔 Telegram ID: {user_id}\\n"
                            f"📚 Tugatilgan mavzular: {completed}\\n"
                            f"📝 Ishlangan testlar: {tests}\\n"
                            f"⭐ Umumiy ball: {score}\\n\\n"
                            "Profilni tahrirlash uchun /editprofile buyrug‘ini yuboring."
                        )
                    else:
                        profile_text = (
                            "👤 TALABA PROFILI\\n\\n"
                            "Profilingiz hali yaratilmagan.\\n"
                            "Ism-familiya va guruhingizni kiritish uchun "
                            "/editprofile buyrug‘ini yuboring."
                        )

            await q.edit_message_text(
                profile_text,
                reply_markup=nav_keyboard(
                    [("📋 ID ni nusxalash", f"copyid:{user_id}")],
                    [home]
                )
            )
            return

        if action == "teacher_panel":
            if admin or not has_access(user_id):
                await q.answer("Bu bo‘lim faqat ustozlar uchun.", show_alert=True)
                return

            with db() as c:
                teacher = c.execute(
                    "SELECT 1 FROM teachers WHERE telegram_id=?",
                    (user_id,)
                ).fetchone()

            if not teacher:
                await q.answer("Bu bo‘lim faqat ustozlar uchun.", show_alert=True)
                return

            await q.edit_message_text(
                "👨‍🏫 USTOZ PANELI\n\nKerakli bo‘limni tanlang:",
                reply_markup=nav_keyboard(
                    [("📊 Prezentatsiyalar", "nav:teacher_presentation")],
                    [("📝 Mustaqil ish", "nav:teacher_independent")],
                    [home]
                )
            )
            return

        if action in ("teacher_presentation", "teacher_independent"):
            if admin:
                await q.answer("Bu bo‘lim faqat ustozlar uchun.", show_alert=True)
                return

            kind = "presentation" if action == "teacher_presentation" else "independent"
            label = "📊 Prezentatsiyalar" if kind == "presentation" else "📝 Mustaqil ish"

            with db() as c:
                teacher = c.execute(
                    "SELECT 1 FROM teachers WHERE telegram_id=?",
                    (user_id,)
                ).fetchone()
                assigned = c.execute(
                    "SELECT s.id, s.name FROM subjects s "
                    "JOIN teacher_subjects ts ON ts.subject_id=s.id "
                    "WHERE ts.teacher_id=? ORDER BY s.name",
                    (user_id,)
                ).fetchall()

            if not teacher:
                await q.answer("Ruxsat yo‘q.", show_alert=True)
                return

            if not assigned:
                await q.edit_message_text(
                    "Sizga hali fan biriktirilmagan.",
                    reply_markup=nav_keyboard([home])
                )
                return

            buttons = [
                [(f"📚 {name}", f"teacher_subject:{kind}:{sid}")]
                for sid, name in assigned
            ]
            buttons.append([home])

            await q.edit_message_text(
                f"{label} — fan tanlang:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(label, callback_data=callback)]
                    for row in buttons for label, callback in row
                ])
            )
            return

        if action.startswith("section:"):
            try:
                section_id = int(action.split(":", 1)[1])
            except ValueError:
                await q.answer("Noto‘g‘ri bo‘lim.", show_alert=True)
                return

            with db() as c:
                section = c.execute(
                    "SELECT name, show_students, show_teachers "
                    "FROM custom_sections WHERE id=? AND is_visible=1",
                    (section_id,)
                ).fetchone()
                is_teacher = c.execute(
                    "SELECT 1 FROM teachers WHERE telegram_id=?",
                    (user_id,)
                ).fetchone() is not None

            allowed = bool(
                section and (
                    admin or
                    (is_teacher and section[2]) or
                    (not is_teacher and section[1])
                )
            )

            if not allowed:
                await q.answer("Bu bo‘lim siz uchun mavjud emas.", show_alert=True)
                return

            if section[0] == "Uyga vazifa":
                with db() as c:
                    rows = c.execute(
                        "SELECT id, title FROM homework_posts "
                        "WHERE is_visible=1 ORDER BY position, id DESC"
                    ).fetchall()

                buttons = [
                    [InlineKeyboardButton(
                        f"📝 {title[:45]}",
                        callback_data=f"hw:view:{hw_id}"
                    )]
                    for hw_id, title in rows
                ]
                buttons.append([InlineKeyboardButton(
                    "🏠 Asosiy menyu", callback_data="nav:home"
                )])

                message = (
                    "📝 UY VAZIFALARI"
                    if rows else "Hozircha e’lon qilingan uy vazifalari yo‘q."
                )
                await q.edit_message_text(
                    message,
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
                return

            with db() as c:
                nodes = c.execute(
                    "SELECT id, name FROM custom_section_nodes "
                    "WHERE root_section_id=? AND parent_id IS NULL AND is_visible=1 "
                    "ORDER BY position, id",
                    (section_id,)
                ).fetchall()
                materials = c.execute(
                    "SELECT id, title, file_name, text_content "
                    "FROM custom_section_materials "
                    "WHERE root_section_id=? AND node_id IS NULL "
                    "ORDER BY position, id",
                    (section_id,)
                ).fetchall()

            buttons = []
            for node_id, name in nodes:
                row = [
                    InlineKeyboardButton(
                        "📂 " + name[:35],
                        callback_data=f"nav:node:{section_id}:{node_id}"
                    )
                ]
                if admin:
                    row.extend([
                        InlineKeyboardButton(
                            "✏️",
                            callback_data=f"nav:renamenode:{section_id}:{node_id}"
                        ),
                        InlineKeyboardButton(
                            "🗑",
                            callback_data=f"nav:deletenode:{section_id}:{node_id}"
                        )
                    ])
                buttons.append(row)

            for material_id, title, filename, content in materials:
                label = title or filename or "Material"
                buttons.append([InlineKeyboardButton(
                    "📎 " + label[:45],
                    callback_data=f"nav:material:{material_id}"
                )])

            if admin:
                buttons.append([InlineKeyboardButton(
                    "➕ Ichki bo‘lim qo‘shish",
                    callback_data=f"nav:addnode:{section_id}:root"
                )])
                buttons.append([InlineKeyboardButton(
                    "📤 Material yuklash",
                    callback_data=f"nav:addmaterial:{section_id}:root"
                )])

            buttons.append([InlineKeyboardButton(
                "🏠 Asosiy menyu", callback_data="nav:home"
            )])

            message = f"📦 {section[0]}"
            if not nodes and not materials:
                message += "\n\nBu bo‘lim hozircha bo‘sh."

            await q.edit_message_text(
                message,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return

        if action.startswith("material:"):
            parts = action.split(":")
            if len(parts) != 2 or not parts[1].isdigit():
                await q.answer("Material manzili noto‘g‘ri.", show_alert=True)
                return

            material_id = int(parts[1])

            with db() as c:
                row = c.execute(
                    "SELECT m.root_section_id, m.node_id, m.title, "
                    "m.text_content, m.file_id, m.file_name, m.mime_type, "
                    "s.show_students, s.show_teachers, s.is_visible, "
                    "n.is_visible "
                    "FROM custom_section_materials m "
                    "JOIN custom_sections s ON s.id=m.root_section_id "
                    "LEFT JOIN custom_section_nodes n ON n.id=m.node_id "
                    "WHERE m.id=?",
                    (material_id,)
                ).fetchone()

                is_teacher = c.execute(
                    "SELECT 1 FROM teachers WHERE telegram_id=?",
                    (user_id,)
                ).fetchone() is not None

            if not row:
                await q.answer("Material topilmadi.", show_alert=True)
                return

            allowed = bool(
                admin or (
                    row[9] and
                    (row[1] is None or row[10]) and
                    ((is_teacher and row[8]) or
                     (not is_teacher and row[7]))
                )
            )

            if not allowed:
                await q.answer("Bu materialni ko‘rishga ruxsatingiz yo‘q.", show_alert=True)
                return

            title, description = row[2], row[3]
            file_id, filename, mime_type = row[4], row[5], row[6]
            caption = title or filename or "Material"
            if description:
                caption += "\\n\\n" + description
            caption = caption[:1024]

            await q.answer()

            if not file_id:
                await q.message.reply_text(caption)
                return

            is_image = (
                (mime_type or "").startswith("image/") or
                (filename or "").lower().endswith(
                    (".jpg", ".jpeg", ".png", ".webp")
                )
            )

            if is_image:
                await q.message.reply_photo(
                    photo=file_id,
                    caption=caption
                )
            else:
                await q.message.reply_document(
                    document=file_id,
                    filename=filename or "material",
                    caption=caption
                )
            return

        if action.startswith("addmaterial:"):
            parts = action.split(":")
            if len(parts) != 3 or not parts[1].isdigit():
                await q.answer("Material manzili noto‘g‘ri.", show_alert=True)
                return

            if not admin:
                await q.answer("Faqat administrator uchun.", show_alert=True)
                return

            root_id = int(parts[1])
            node_id = None if parts[2] == "root" else (
                int(parts[2]) if parts[2].isdigit() else -1
            )

            with db() as c:
                root = c.execute(
                    "SELECT id FROM custom_sections WHERE id=?",
                    (root_id,)
                ).fetchone()
                parent_ok = (
                    node_id is None or
                    c.execute(
                        "SELECT id FROM custom_section_nodes "
                        "WHERE id=? AND root_section_id=?",
                        (node_id, root_id)
                    ).fetchone()
                )

            if not root or not parent_ok:
                await q.answer("Bo‘lim topilmadi.", show_alert=True)
                return

            context.user_data.clear()
            context.user_data["custom_material_root_id"] = root_id
            context.user_data["custom_material_node_id"] = node_id
            context.user_data["waiting_custom_material_title"] = True

            await q.message.reply_text(
                "📎 Material uchun nom yuboring.\n"
                "Masalan: Bosh miya nervlari — taqdimot\n\n"
                "Bekor qilish: /cancel"
            )
            return

        if action.startswith("addnode:"):
            parts = action.split(":")
            if len(parts) != 3 or not parts[1].isdigit():
                await q.answer("Manzil noto‘g‘ri.", show_alert=True)
                return

            if not admin:
                await q.answer("Faqat administrator uchun.", show_alert=True)
                return

            section_id = int(parts[1])
            parent_id = None if parts[2] == "root" else (
                int(parts[2]) if parts[2].isdigit() else -1
            )

            with db() as c:
                section = c.execute(
                    "SELECT id FROM custom_sections WHERE id=?",
                    (section_id,)
                ).fetchone()

                parent_ok = (
                    parent_id is None or
                    c.execute(
                        "SELECT id FROM custom_section_nodes "
                        "WHERE id=? AND root_section_id=?",
                        (parent_id, section_id)
                    ).fetchone()
                )

            if not section or not parent_ok:
                await q.answer("Bo‘lim topilmadi.", show_alert=True)
                return

            context.user_data.clear()
            context.user_data["waiting_custom_node_name"] = True
            context.user_data["custom_node_root_id"] = section_id
            context.user_data["custom_node_parent_id"] = parent_id

            await q.message.reply_text(
                "📂 Yangi ichki bo‘lim nomini yuboring.\n"
                "Bekor qilish: /cancel"
            )
            return

        if action.startswith("node:"):
            parts = action.split(":")
            if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
                await q.answer("Bo‘lim manzili noto‘g‘ri.", show_alert=True)
                return

            section_id, node_id = int(parts[1]), int(parts[2])

            with db() as c:
                node = c.execute(
                    "SELECT name, parent_id FROM custom_section_nodes "
                    "WHERE id=? AND root_section_id=? AND is_visible=1",
                    (node_id, section_id)
                ).fetchone()
                root = c.execute(
                    "SELECT show_students, show_teachers FROM custom_sections "
                    "WHERE id=? AND is_visible=1",
                    (section_id,)
                ).fetchone()
                is_teacher = c.execute(
                    "SELECT 1 FROM teachers WHERE telegram_id=?",
                    (user_id,)
                ).fetchone() is not None

                children = c.execute(
                    "SELECT id, name FROM custom_section_nodes "
                    "WHERE root_section_id=? AND parent_id=? AND is_visible=1 "
                    "ORDER BY position, id",
                    (section_id, node_id)
                ).fetchall()
                materials = c.execute(
                    "SELECT id, title, file_name FROM custom_section_materials "
                    "WHERE root_section_id=? AND node_id=? ORDER BY position, id",
                    (section_id, node_id)
                ).fetchall()

            allowed = bool(root and (
                admin or (is_teacher and root[1]) or (not is_teacher and root[0])
            ))
            if not node or not allowed:
                await q.answer("Bo‘lim topilmadi yoki ruxsatingiz yo‘q.", show_alert=True)
                return

            buttons = []
            for child_id, name in children:
                row = [
                    InlineKeyboardButton(
                        "📂 " + name[:35],
                        callback_data=f"nav:node:{section_id}:{child_id}"
                    )
                ]
                if admin:
                    row.extend([
                        InlineKeyboardButton(
                            "✏️",
                            callback_data=f"nav:renamenode:{section_id}:{child_id}"
                        ),
                        InlineKeyboardButton(
                            "🗑",
                            callback_data=f"nav:deletenode:{section_id}:{child_id}"
                        )
                    ])
                buttons.append(row)

            for material_id, title, filename in materials:
                buttons.append([InlineKeyboardButton(
                    "📎 " + (title or filename or "Material")[:45],
                    callback_data=f"nav:material:{material_id}"
                )])

            if admin:
                buttons.append([InlineKeyboardButton(
                    "➕ Ichki bo‘lim qo‘shish",
                    callback_data=f"nav:addnode:{section_id}:{node_id}"
                )])
                buttons.append([InlineKeyboardButton(
                    "📤 Material yuklash",
                    callback_data=f"nav:addmaterial:{section_id}:{node_id}"
                )])

            if admin:
                buttons.append([InlineKeyboardButton(
                    "✏️ Papka nomini o'zgartirish",
                    callback_data=f"nav:renamenode:{section_id}:{node_id}"
                )])
                buttons.append([InlineKeyboardButton(
                    "🗑 Papkani o'chirish",
                    callback_data=f"nav:deletenode:{section_id}:{node_id}"
                )])

            back_id = node[1]
            back_callback = (
                f"nav:node:{section_id}:{back_id}"
                if back_id is not None else f"nav:section:{section_id}"
            )
            buttons.append([InlineKeyboardButton("⬅️ Orqaga", callback_data=back_callback)])
            buttons.append([InlineKeyboardButton("🏠 Asosiy menyu", callback_data="nav:home")])

            message = f"📂 {node[0]}"
            if not children and not materials:
                message += "\\n\\nBu bo‘lim hozircha bo‘sh."

            await q.edit_message_text(
                message,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return

        await q.answer("Bu menyu bo‘limi hali ulanmagan.", show_alert=True)
        return

    if data.startswith("copyid:"):
        owner_id = int(data.split(":", 1)[1])
        if q.from_user.id != owner_id:
            await q.answer("Bu tugma sizning profilingizga tegishli emas.", show_alert=True)
            return
        await q.message.reply_text(f"🆔 Telegram ID: {owner_id}\n\nUshbu raqamni bosib turib nusxalashingiz mumkin.")
        return

    if data.startswith("assignteacher:"):
        if q.from_user.id != ADMIN_ID:
            await q.answer("Ruxsat yo‘q.", show_alert=True)
            return
        teacher_id = int(data.split(":", 1)[1])
        with db() as c:
            teacher = c.execute(
                "SELECT telegram_id FROM teachers WHERE telegram_id=?",
                (teacher_id,)
            ).fetchone()
            available_subjects = c.execute(
                "SELECT id, name FROM subjects ORDER BY name"
            ).fetchall()
        if not teacher:
            await q.message.reply_text("Ustoz ro‘yxatda topilmadi.")
            return
        if not available_subjects:
            await q.message.reply_text("Avval fan qo‘shing.")
            return
        buttons = []
        for sid, name in available_subjects:
            buttons.append([InlineKeyboardButton(
                f"🎓 {name}", callback_data=f"assignsubject:{teacher_id}:{sid}"
            )])
        await q.message.reply_text(
            f"👨‍🏫 Ustoz: {teacher_id}\nQaysi fanni biriktiramiz?",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    if data.startswith("assignsubject:"):
        if q.from_user.id != ADMIN_ID:
            await q.answer("Ruxsat yo‘q.", show_alert=True)
            return
        _, raw_teacher_id, raw_subject_id = data.split(":")
        teacher_id, subject_id = int(raw_teacher_id), int(raw_subject_id)
        with db() as c:
            teacher = c.execute(
                "SELECT 1 FROM teachers WHERE telegram_id=?", (teacher_id,)
            ).fetchone()
            subject_row = c.execute(
                "SELECT name FROM subjects WHERE id=?", (subject_id,)
            ).fetchone()
            if teacher and subject_row:
                c.execute(
                    "INSERT OR IGNORE INTO teacher_subjects (teacher_id, subject_id) VALUES (?, ?)",
                    (teacher_id, subject_id)
                )
        if not teacher or not subject_row:
            await q.message.reply_text("Ustoz yoki fan topilmadi.")
            return
        await q.message.reply_text(
            f"✅ {subject_row[0]} fani {teacher_id} ID raqamli ustozga biriktirildi."
        )
        return

    if data.startswith(("removeuser:", "confirmremoveuser:", "cancelremoveuser:")):
        if q.from_user.id != ADMIN_ID:
            await q.answer("Ruxsat yo‘q.", show_alert=True)
            return

        action, raw_id = data.split(":", 1)
        target_id = int(raw_id)

        if target_id == ADMIN_ID:
            await q.answer("Administratorni o‘chirib bo‘lmaydi.", show_alert=True)
            return

        with db() as c:
            student = c.execute(
                "SELECT id, full_name FROM students WHERE telegram_id = ?",
                (target_id,)
            ).fetchone()
            teacher = c.execute(
                "SELECT 1 FROM teachers WHERE telegram_id = ?",
                (target_id,)
            ).fetchone()
            request = c.execute(
                "SELECT full_name, status FROM access_requests WHERE telegram_id = ?",
                (target_id,)
            ).fetchone()

        if not student and not teacher and not request:
            await q.edit_message_text("ℹ️ Foydalanuvchi topilmadi.")
            return

        name = student[1] if student else (
            request[0] if request else "Noma’lum"
        )
        roles = []
        if student:
            roles.append("Talaba")
        if teacher:
            roles.append("Ustoz")
        if request:
            roles.append("Kirish so‘rovi: " + request[1])

        if action == "removeuser":
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🗑 Ha, butunlay o‘chirish",
                        callback_data=f"confirmremoveuser:{target_id}"
                    ),
                    InlineKeyboardButton(
                        "↩️ Bekor qilish",
                        callback_data=f"cancelremoveuser:{target_id}"
                    )
                ]
            ])
            await q.edit_message_text(
                "⚠️ FOYDALANUVCHINI BUTUNLAY O‘CHIRISH\n\n"
                f"Ism: {name}\n"
                f"Telegram ID: {target_id}\n"
                f"Rollar: {', '.join(roles)}\n\n"
                "Uning profili, statistikasi, test natijalari, "
                "kirish ma’lumotlari va barcha rollari o‘chiriladi. "
                "Umumiy fanlar, mavzular va materiallar saqlanadi.\n\n"
                "Davom etishni tasdiqlaysanmi?",
                reply_markup=keyboard
            )
            return

        if action == "cancelremoveuser":
            await q.edit_message_text(
                "↩️ O‘chirish bekor qilindi. Foydalanuvchi saqlab qolindi.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "⬅️ Foydalanuvchilar ro‘yxati",
                        callback_data="nav:users"
                    )
                ]])
            )
            return

        if action == "confirmremoveuser":
            with db() as c:
                student_row = c.execute(
                    "SELECT id FROM students WHERE telegram_id = ?",
                    (target_id,)
                ).fetchone()

                if student_row:
                    student_id = student_row[0]
                    c.execute(
                        "DELETE FROM student_logins WHERE student_id = ?",
                        (student_id,)
                    )
                    c.execute(
                        "DELETE FROM quiz_attempts WHERE student_id = ?",
                        (student_id,)
                    )
                    c.execute(
                        "DELETE FROM topic_progress WHERE student_id = ?",
                        (student_id,)
                    )
                    c.execute(
                        "DELETE FROM student_stats WHERE student_id = ?",
                        (student_id,)
                    )
                    c.execute(
                        "DELETE FROM students WHERE id = ?",
                        (student_id,)
                    )

                c.execute(
                    "DELETE FROM teacher_subjects WHERE teacher_id = ?",
                    (target_id,)
                )
                c.execute(
                    "DELETE FROM teachers WHERE telegram_id = ?",
                    (target_id,)
                )
                c.execute(
                    "DELETE FROM access_requests WHERE telegram_id = ?",
                    (target_id,)
                )

            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text="🚫 MedStudy platformasiga kirish huquqingiz bekor qilindi. "
                         "Qayta kirish uchun /start orqali yangi so‘rov yuborishingiz mumkin."
                )
            except Exception:
                pass

            await q.edit_message_text(
                f"✅ {name} (ID: {target_id}) platformadan butunlay o‘chirildi. "
                "Shaxsiy ma’lumotlari va rollari olib tashlandi.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "⬅️ Foydalanuvchilar ro‘yxati",
                        callback_data="nav:users"
                    )
                ]])
            )
            return

    if data.startswith(("removeteacher:", "confirmremoveteacher:", "cancelremoveteacher:")):
        if q.from_user.id != ADMIN_ID:
            await q.answer("Ruxsat yo‘q.", show_alert=True)
            return

        action, raw_id = data.split(":", 1)
        teacher_id = int(raw_id)

        with db() as c:
            teacher = c.execute(
                "SELECT telegram_id FROM teachers WHERE telegram_id = ?",
                (teacher_id,)
            ).fetchone()

            if not teacher:
                await q.edit_message_text("ℹ️ Bu ustoz ro‘yxatda topilmadi.")
                return

            if action == "removeteacher":
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "✅ Ha, bekor qilish",
                            callback_data=f"confirmremoveteacher:{teacher_id}"
                        ),
                        InlineKeyboardButton(
                            "↩️ Bekor qilish",
                            callback_data=f"cancelremoveteacher:{teacher_id}"
                        )
                    ]
                ])
                await q.edit_message_text(
                    f"⚠️ {teacher_id} ID raqamli ustozning ruxsatini bekor qilmoqchimisiz?",
                    reply_markup=keyboard
                )
                return

            if action == "confirmremoveteacher":
                c.execute(
                    "DELETE FROM teachers WHERE telegram_id = ?",
                    (teacher_id,)
                )
                await q.edit_message_text(
                    f"✅ {teacher_id} ID raqamli ustozning ruxsati bekor qilindi."
                )
                return

            if action == "cancelremoveteacher":
                await q.edit_message_text("↩️ Amal bekor qilindi. Ustoz ro‘yxatda qoldi.")
                return

    if data.startswith(("renamesection:", "togglesection:", "togglestudents:", "toggleteachers:", "deletesection:", "confirmdeletesection:", "cancelsection:")):
        if q.from_user.id != ADMIN_ID:
            await q.answer("Ruxsat yo‘q.", show_alert=True)
            return

        action, raw_id = data.split(":", 1)
        section_id = int(raw_id)

        with db() as c:
            item = c.execute(
                "SELECT id, name FROM custom_sections WHERE id = ?",
                (section_id,)
            ).fetchone()

            if not item:
                await q.answer("Bo‘lim topilmadi.", show_alert=True)
                return

            if action == "renamesection":
                context.user_data.clear()
                context.user_data["waiting_section_name"] = True
                context.user_data["rename_section_id"] = section_id
                await q.message.reply_text(
                    f"✏️ Hozirgi nomi: {item[1]}\\nYangi nomini yuboring. Bekor qilish: /cancel"
                )
                return

            if action == "togglesection":
                c.execute(
                    "UPDATE custom_sections SET is_visible = CASE WHEN is_visible = 1 THEN 0 ELSE 1 END WHERE id = ?",
                    (section_id,)
                )
                await q.message.reply_text("✅ Bo‘lim ko‘rinish holati almashtirildi.")
                return

            if action == "togglestudents":
                c.execute(
                    "UPDATE custom_sections SET show_students = CASE WHEN show_students = 1 THEN 0 ELSE 1 END WHERE id = ?",
                    (section_id,)
                )
                await q.message.reply_text("✅ Talabalar uchun ko‘rinish holati almashtirildi.")
                return

            if action == "toggleteachers":
                c.execute(
                    "UPDATE custom_sections SET show_teachers = CASE WHEN show_teachers = 1 THEN 0 ELSE 1 END WHERE id = ?",
                    (section_id,)
                )
                await q.message.reply_text("✅ Ustozlar uchun ko‘rinish holati almashtirildi.")
                return

            if action == "deletesection":
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🗑 Ha, o‘chir", callback_data=f"confirmdeletesection:{section_id}")],
                    [InlineKeyboardButton("❌ Bekor qilish", callback_data=f"cancelsection:{section_id}")]
                ])
                await q.message.reply_text(
                    f"⚠️ «{item[1]}» bo‘limini o‘chirishni tasdiqlaysizmi?",
                    reply_markup=keyboard
                )
                return

            if action == "confirmdeletesection":
                c.execute("DELETE FROM custom_sections WHERE id = ?", (section_id,))
                await q.message.reply_text("✅ Bo‘lim o‘chirildi.")
                return

            if action == "cancelsection":
                await q.message.reply_text("❎ O‘chirish bekor qilindi.")
                return

    if data == "all_subjects":
        await show_subjects(q)
        return

    if data.startswith("renamesubject:"):
        if q.from_user.id != ADMIN_ID:
            await q.answer("Ruxsat yo'q.", show_alert=True)
            return

        sid = int(data.split(":", 1)[1])
        item = subject(sid)
        if not item:
            await q.answer("Fan topilmadi.", show_alert=True)
            return

        context.user_data.clear()
        context.user_data["waiting_subject_name"] = True
        context.user_data["rename_subject_id"] = sid
        await q.answer()
        await q.message.reply_text(
            f"✏️ Hozirgi fan nomi: {item[1]}\\n"
            "Yangi nomini yuboring. Bekor qilish uchun /cancel."
        )
        return

    if data.startswith("deletesubject:"):
        if q.from_user.id != ADMIN_ID:
            await q.answer("Ruxsat yo'q.", show_alert=True)
            return

        sid = int(data.split(":", 1)[1])
        item = subject(sid)
        if not item:
            await q.answer("Fan topilmadi.", show_alert=True)
            return

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🗑 Ha, hammasini o'chirish",
                    callback_data=f"confirmdeletesubject:{sid}"
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ Bekor qilish",
                    callback_data=f"canceldeletesubject:{sid}"
                )
            ]
        ])
        await q.answer()
        await q.message.reply_text(
            f"⚠️ «{item[1]}» fanini o'chirmoqchimisiz?\\n\\n"
            "Unga tegishli barcha mavzular, PDF materiallar "
            "va mavzu natijalari ham o'chadi. Bu amalni qaytarib bo'lmaydi.",
            reply_markup=keyboard
        )
        return

    if data.startswith("confirmdeletesubject:"):
        if q.from_user.id != ADMIN_ID:
            await q.answer("Ruxsat yo'q.", show_alert=True)
            return

        sid = int(data.split(":", 1)[1])
        item = subject(sid)
        if not item:
            await q.answer("Fan topilmadi.", show_alert=True)
            return

        with db() as c:
            c.execute(
                "DELETE FROM materials WHERE topic_id IN "
                "(SELECT id FROM topics WHERE subject_id=?)",
                (sid,)
            )
            c.execute(
                "DELETE FROM topic_progress WHERE topic_id IN "
                "(SELECT id FROM topics WHERE subject_id=?)",
                (sid,)
            )
            c.execute("DELETE FROM topics WHERE subject_id=?", (sid,))
            c.execute("DELETE FROM subjects WHERE id=?", (sid,))

        await q.answer("Fan va unga tegishli ma'lumotlar o'chirildi.")
        await q.message.reply_text(
            f"✅ «{item[1]}» fani va unga tegishli barcha ma'lumotlar o'chirildi."
        )
        await show_subjects(q.message, user_id=q.from_user.id)
        return

    if data.startswith("canceldeletesubject:"):
        if q.from_user.id != ADMIN_ID:
            await q.answer("Ruxsat yo'q.", show_alert=True)
            return

        await q.answer("O'chirish bekor qilindi.")
        await q.message.reply_text("❎ Fan o'chirilmadi.")
        await show_subjects(q.message, user_id=q.from_user.id)
        return

    if data.startswith("topicpage:") and data != "topicpage:noop":
        parts = data.split(":")
        if len(parts) == 4:
            sid = int(parts[1])
            page = int(parts[2])
            pdf_mode = parts[3] == "1"
            await show_topics(q, sid, pdf_mode=pdf_mode, page=page)
        return

    if data == "topicpage:noop":
        return

    if data.startswith("subject:"):
        await show_topics(q, int(data.split(":")[1]))
        return

    if data.startswith("addtopics:"):
        if not admin:
            await q.message.reply_text("⛔ Ruxsat yo'q.")
            return
        sid = int(data.split(":")[1])
        if not subject(sid):
            await q.message.reply_text("Fan topilmadi.")
            return
        context.user_data.clear()
        context.user_data["waiting_topics_batch"] = True
        context.user_data["batch_subject_id"] = sid
        await q.message.reply_text(
            "📚 KTP mavzularini kiriting.\n\n"
            "Har bir mavzuni yangi qatordan yozing.\n"
            "Masalan:\n"
            "Uzunchoq miya\n"
            "Miyacha anatomiyasi\n"
            "Bosh miya ko'prigi\n\n"
            "Yuborilgan mavzular birma-bir saqlanadi.\n"
            "Bekor qilish: /cancel"
        )
        return

    if data.startswith("addtopic:"):
        if not admin:
            await q.message.reply_text("⛔ Ruxsat yo'q.")
            return
        sid = int(data.split(":")[1])
        if not subject(sid):
            await q.message.reply_text("Fan topilmadi.")
            return
        context.user_data.clear()
        context.user_data["waiting_subject"] = True
        context.user_data["subject_id"] = sid
        await q.message.reply_text(
            "📖 Yangi mavzu nomini yuboring.\nBekor qilish: /cancel"
        )
        return

    if data.startswith("teacher_subject:"):
        if admin:
            await q.answer("Bu bo‘lim ustozlar uchun.", show_alert=True)
            return
        parts = data.split(":")
        if len(parts) != 3:
            return
        kind, sid = parts[1], int(parts[2])
        with db() as c:
            allowed = c.execute(
                "SELECT 1 FROM teacher_subjects ts "
                "JOIN teachers t ON t.telegram_id=ts.teacher_id "
                "WHERE ts.teacher_id=? AND ts.subject_id=?",
                (q.from_user.id, sid)
            ).fetchone()
            items = c.execute(
                "SELECT id, name FROM topics WHERE subject_id=? ORDER BY id",
                (sid,)
            ).fetchall() if allowed else []
            subject_row = c.execute(
                "SELECT name FROM subjects WHERE id=?", (sid,)
            ).fetchone() if allowed else None
        if not allowed or not subject_row:
            await q.answer("Bu fan sizga biriktirilmagan.", show_alert=True)
            return
        buttons = [
            [InlineKeyboardButton(
                name, callback_data=f"teacher_topic:{kind}:{tid}"
            )]
            for tid, name in items
        ]
        buttons.append([InlineKeyboardButton("⬅️ Fanlar", callback_data=f"teacher_back:{kind}")])
        await q.edit_message_text(
            f"📚 {subject_row[0]} — mavzuni tanlang:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    if data.startswith("teacher_topic:"):
        if admin:
            await q.answer("Bu bo‘lim ustozlar uchun.", show_alert=True)
            return
        parts = data.split(":")
        if len(parts) != 3:
            return
        kind, tid = parts[1], int(parts[2])
        with db() as c:
            row = c.execute(
                "SELECT t.name, t.subject_id FROM topics t "
                "JOIN teacher_subjects ts ON ts.subject_id=t.subject_id "
                "JOIN teachers tr ON tr.telegram_id=ts.teacher_id "
                "WHERE t.id=? AND ts.teacher_id=?",
                (tid, q.from_user.id)
            ).fetchone()
            mats = c.execute(
                "SELECT id, title FROM materials "
                "WHERE topic_id=? AND material_type=? ORDER BY id",
                (tid, kind)
            ).fetchall() if row else []
        if not row:
            await q.answer("Bu mavzuga ruxsatingiz yo‘q.", show_alert=True)
            return
        buttons = [
            [InlineKeyboardButton(f"📄 {title}", callback_data=f"material:{mid}")]
            for mid, title in mats
        ]
        buttons.append([InlineKeyboardButton(
            "⬅️ Mavzular", callback_data=f"teacher_subject:{kind}:{row[1]}"
        )])
        await q.edit_message_text(
            f"📖 {row[0]}\n\n" +
            ("Materiallar:" if mats else "Bu bo‘limda hozircha fayl yo‘q."),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    if data.startswith("teacher_back:"):
        kind = data.split(":", 1)[1]
        with db() as c:
            items = c.execute(
                "SELECT s.id, s.name FROM subjects s "
                "JOIN teacher_subjects ts ON ts.subject_id=s.id "
                "WHERE ts.teacher_id=? ORDER BY s.name",
                (q.from_user.id,)
            ).fetchall()
        buttons = [
            [InlineKeyboardButton(name, callback_data=f"teacher_subject:{kind}:{sid}")]
            for sid, name in items
        ]
        await q.edit_message_text(
            "Fan tanlang:", reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    if data.startswith("topicsection:"):
        parts = data.split(":")
        if len(parts) != 3 or parts[1] not in (
            "presentation", "independent", "student_topic"
        ):
            return
        kind, tid = parts[1], int(parts[2])
        t = topic(tid)
        if not t:
            await q.answer("Mavzu topilmadi.", show_alert=True)
            return

        if not admin:
            with db() as c:
                allowed = c.execute(
                    "SELECT 1 FROM teacher_subjects "
                    "WHERE teacher_id=? AND subject_id=?",
                    (user_id, t[1])
                ).fetchone()
            if not allowed or kind == "student_topic":
                await q.answer("⛔ Bu bo‘limga ruxsatingiz yo‘q.", show_alert=True)
                return

        with db() as c:
            mats = c.execute(
                "SELECT id, title FROM materials "
                "WHERE topic_id=? AND material_type=? ORDER BY id",
                (tid, kind)
            ).fetchall()

        labels = {
            "presentation": "📊 Prezentatsiya",
            "independent": "📝 Mustaqil ish",
            "student_topic": "📚 Eski talabalar materiallari",
        }
        buttons = []
        for mid, title in mats:
            buttons.append([
                InlineKeyboardButton(f"📄 {title}", callback_data=f"material:{mid}")
            ])
            if admin:
                buttons.append([
                    InlineKeyboardButton("✏️", callback_data=f"renamepdf:{mid}"),
                    InlineKeyboardButton("🔄", callback_data=f"replacepdf:{mid}"),
                    InlineKeyboardButton("🗑", callback_data=f"deletepdf:{mid}")
                ])

        if admin and kind != "student_topic":
            buttons.append([
                InlineKeyboardButton(
                    "➕ PDF / PPTX qo‘shish",
                    callback_data=f"uploadtype:{kind}:{tid}"
                )
            ])
        if admin and kind == "student_topic":
            buttons.append([
                InlineKeyboardButton("➕ Material qo‘shish", callback_data=f"uploadtype:{kind}:{tid}")
            ])

        buttons.append([
            InlineKeyboardButton("⬅️ Mavzuga qaytish", callback_data=f"topic:{tid}")
        ])
        await q.edit_message_text(
            f"📖 {t[2]}\n\n{labels[kind]}\n"
            + (f"Materiallar: {len(mats)} ta" if mats else "Hozircha fayl yo‘q."),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    if data.startswith("topic:"):
        await show_topic(q, int(data.split(":")[1]))
        return

    if data.startswith("uploadtype:"):
        if not admin:
            await q.answer("Faqat administrator uchun.", show_alert=True)
            return
        parts = data.split(":")
        if len(parts) != 3 or parts[1] not in ("presentation", "independent", "student_topic"):
            return
        kind, tid = parts[1], int(parts[2])
        if not topic(tid):
            await q.message.reply_text("Mavzu topilmadi.")
            return
        context.user_data.clear()
        context.user_data["waiting_pdf"] = True
        context.user_data["topic_id"] = tid
        context.user_data["material_type"] = kind
        await q.message.reply_text(
            "📄 Tanlangan bo‘lim uchun PDF faylni yuboring.\\n"
            "Faqat PDF qabul qilinadi.\\n"
            "Bekor qilish: /cancel"
        )
        return

    if data.startswith("addpdf:"):
        if not admin:
            await q.message.reply_text("⛔ Ruxsat yo‘q.")
            return
        tid = int(data.split(":")[1])
        if not topic(tid):
            await q.message.reply_text("Mavzu topilmadi.")
            return
        buttons = [
            [InlineKeyboardButton("📊 Prezentatsiya", callback_data=f"uploadtype:presentation:{tid}")],
            [InlineKeyboardButton("📝 Mustaqil ish", callback_data=f"uploadtype:independent:{tid}")],
            [InlineKeyboardButton("📚 Mavzu uchun (talabalar)", callback_data=f"uploadtype:student_topic:{tid}")]
        ]
        await q.message.reply_text(
            "Fayl qaysi bo‘limga tegishli?",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    if data == "choose_pdf_subject":
        await show_subjects(q.message, "pdf_subject")
        return

    if data.startswith("pdf_subject:"):
        await show_topics(q, int(data.split(":")[1]), pdf_mode=True)
        return

    if data.startswith("pdf_topic:"):
        if not admin:
            await q.message.reply_text("⛔ Ruxsat yo‘q.")
            return
        tid = int(data.split(":")[1])
        if not topic(tid):
            await q.message.reply_text("Mavzu topilmadi.")
            return
        buttons = [
            [InlineKeyboardButton("📊 Prezentatsiya", callback_data=f"uploadtype:presentation:{tid}")],
            [InlineKeyboardButton("📝 Mustaqil ish", callback_data=f"uploadtype:independent:{tid}")],
            [InlineKeyboardButton("📚 Mavzu uchun (talabalar)", callback_data=f"uploadtype:student_topic:{tid}")]
        ]
        await q.message.reply_text(
            "Fayl qaysi bo‘limga tegishli?",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    if data.startswith("replacepdf:"):
        if not admin:
            await q.message.reply_text("⛔ Ruxsat yo'q.")
            return
        mid = int(data.split(":")[1])
        with db() as c:
            row = c.execute(
                "SELECT topic_id, title FROM materials WHERE id=?", (mid,)
            ).fetchone()
        if not row:
            await q.message.reply_text("Material topilmadi.")
            return
        context.user_data.clear()
        context.user_data["waiting_pdf"] = True
        context.user_data["topic_id"] = row[0]
        context.user_data["replace_material_id"] = mid
        await q.message.reply_text(
            f"🔄 «{row[1]}» o'rniga yangi PDF yuboring.\\n"
            "Bekor qilish: /cancel"
        )
        return

    if data.startswith("deletepdf:"):
        if not admin:
            await q.message.reply_text("⛔ Ruxsat yo'q.")
            return
        mid = int(data.split(":")[1])
        with db() as c:
            row = c.execute(
                "SELECT title FROM materials WHERE id=?", (mid,)
            ).fetchone()
        if not row:
            await q.message.reply_text("Material topilmadi.")
            return
        buttons = [[
            InlineKeyboardButton(
                "✅ Ha, o'chir", callback_data=f"confirmdeletepdf:{mid}"
            ),
            InlineKeyboardButton(
                "❌ Bekor qilish", callback_data=f"canceldeletepdf:{mid}"
            )
        ]]
        await q.message.reply_text(
            f"🗑 «{row[0]}» PDFni o'chirishni tasdiqlaysizmi?",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    if data.startswith("confirmdeletepdf:"):
        if not admin:
            await q.message.reply_text("⛔ Ruxsat yo'q.")
            return
        mid = int(data.split(":")[1])
        with db() as c:
            row = c.execute(
                "SELECT topic_id FROM materials WHERE id=?", (mid,)
            ).fetchone()
            if row:
                c.execute("DELETE FROM materials WHERE id=?", (mid,))
        if not row:
            await q.message.reply_text("Material topilmadi.")
            return
        await show_topic(q, row[0])
        return

    if data.startswith("canceldeletepdf:"):
        if not admin:
            await q.message.reply_text("⛔ Ruxsat yo'q.")
            return
        mid = int(data.split(":")[1])
        with db() as c:
            row = c.execute(
                "SELECT topic_id FROM materials WHERE id=?", (mid,)
            ).fetchone()
        if row:
            await show_topic(q, row[0])
        else:
            await q.message.reply_text("Material topilmadi.")
        return

    if data.startswith("renametopic:"):
        if q.from_user.id != ADMIN_ID:
            await q.answer("Faqat administrator uchun.", show_alert=True)
            return
        tid = int(data.split(":")[1])
        t = topic(tid)
        if not t:
            await q.message.reply_text("Mavzu topilmadi.")
            return
        context.user_data.clear()
        context.user_data["rename_topic_id"] = tid
        context.user_data["waiting_topic_name"] = True
        await q.message.reply_text(
            f"Hozirgi nom: {t[2]}\\nYangi mavzu nomini yuboring.\\nBekor qilish: /cancel"
        )
        return

    if data.startswith("deletetopic:"):
        if not admin:
            await q.answer("Faqat administrator uchun.", show_alert=True)
            return
        tid = int(data.split(":")[1])
        t = topic(tid)
        if not t:
            await q.message.reply_text("Mavzu topilmadi.")
            return
        buttons = [[
            InlineKeyboardButton(
                "✅ Ha, mavzuni o'chir",
                callback_data=f"confirmdeletetopic:{tid}"
            ),
            InlineKeyboardButton(
                "❌ Bekor qilish",
                callback_data=f"canceldeletetopic:{tid}"
            )
        ]]
        await q.message.reply_text(
            f"⚠️ «{t[2]}» mavzusini va unga biriktirilgan PDF materiallarni o'chirishni tasdiqlaysizmi?",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    if data.startswith("confirmdeletetopic:"):
        if not admin:
            await q.answer("Faqat administrator uchun.", show_alert=True)
            return
        tid = int(data.split(":")[1])
        with db() as c:
            row = c.execute(
                "SELECT subject_id, name FROM topics WHERE id=?", (tid,)
            ).fetchone()
            if row:
                c.execute("DELETE FROM materials WHERE topic_id=?", (tid,))
                c.execute("DELETE FROM topic_progress WHERE topic_id=?", (tid,))
                c.execute("DELETE FROM topics WHERE id=?", (tid,))
        if not row:
            await q.message.reply_text("Mavzu topilmadi.")
            return
        await q.message.reply_text(f"🗑 «{row[1]}» mavzusi o'chirildi.")
        await show_topics(q, row[0])
        return

    if data.startswith("canceldeletetopic:"):
        if not admin:
            await q.answer("Faqat administrator uchun.", show_alert=True)
            return
        tid = int(data.split(":")[1])
        await show_topic(q, tid)
        return

    if data.startswith("renamepdf:"):
        if not admin:
            await q.answer("Faqat administrator uchun.", show_alert=True)
            return
        mid = int(data.split(":")[1])
        with db() as c:
            row = c.execute(
                "SELECT title FROM materials WHERE id=?", (mid,)
            ).fetchone()
        if not row:
            await q.message.reply_text("Material topilmadi.")
            return
        context.user_data.clear()
        context.user_data["rename_material_id"] = mid
        context.user_data["waiting_pdf_name"] = True
        await q.message.reply_text(
            f"Hozirgi nom: {row[0]}\\nYangi PDF nomini yuboring.\\nBekor qilish: /cancel"
        )
        return

    if data.startswith("material:"):
        try:
            mid = int(data.split(":", 1)[1])
        except (ValueError, IndexError):
            await q.message.reply_text("⚠️ Material ID noto‘g‘ri.")
            return

        user_id = q.from_user.id
        with db() as c:
            row = c.execute(
                "SELECT m.title, m.file_id, m.material_type, t.subject_id "
                "FROM materials m JOIN topics t ON t.id=m.topic_id "
                "WHERE m.id=?",
                (mid,)
            ).fetchone()

            allowed = False
            if row and user_id == ADMIN_ID:
                allowed = True
            elif row:
                title, file_id, material_type, subject_id = row

                is_student = c.execute(
                    "SELECT 1 FROM students WHERE telegram_id=?",
                    (user_id,)
                ).fetchone() is not None

                is_teacher = c.execute(
                    "SELECT 1 FROM teachers WHERE telegram_id=?",
                    (user_id,)
                ).fetchone() is not None

                if material_type == "student_topic" and is_student:
                    allowed = True
                elif material_type in ("presentation", "independent") and is_teacher:
                    assigned = c.execute(
                        "SELECT 1 FROM teacher_subjects "
                        "WHERE teacher_id=? AND subject_id=?",
                        (user_id, subject_id)
                    ).fetchone() is not None
                    allowed = assigned

        if not row:
            await q.message.reply_text("Material topilmadi.")
            return

        if not allowed:
            await q.message.reply_text(
                "⛔ Sizda ushbu materialni ko‘rish uchun ruxsat yo‘q."
            )
            return

        await q.message.reply_document(
            document=row[1], caption=f"📘 {row[0]}"
        )
        return


async def receive_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("⛔ PDF qo'shish faqat administrator uchun.")
        return

    if context.user_data.get("waiting_custom_material_files"):
        document = update.message.document
        if not document:
            await update.message.reply_text("Faylni hujjat sifatida yuboring.")
            return

        filename = document.file_name or "material"
        ext = Path(filename).suffix.lower()
        allowed = {".pdf", ".pptx", ".docx", ".jpg", ".jpeg", ".png", ".webp", ".txt"}

        if ext not in allowed:
            await update.message.reply_text(
                "⛔ Bu format qo‘llab-quvvatlanmaydi. PDF, PPTX, DOCX, "
                "JPG, PNG, WEBP yoki TXT yuboring."
            )
            return

        with db() as c:
            c.execute(
                "INSERT INTO custom_section_materials "
                "(root_section_id, node_id, material_type, title, text_content, "
                "file_id, file_name, mime_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    context.user_data["custom_material_root_id"],
                    context.user_data.get("custom_material_node_id"),
                    "file",
                    context.user_data["custom_material_title"],
                    context.user_data.get("custom_material_description", ""),
                    document.file_id,
                    filename,
                    document.mime_type or ""
                )
            )

        count = context.user_data.get("custom_material_count", 0) + 1
        context.user_data["custom_material_count"] = count

        await update.message.reply_text(
            f"✅ Saqlandi: {filename}\n📎 Jami fayllar: {count}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "✅ Yuklashni tugatish",
                    callback_data="nav:finishmaterial"
                )
            ]])
        )
        return

    if not context.user_data.get("waiting_pdf"):
        await update.message.reply_text(
            "PDF qo'shish uchun avval menyudan 📄 PDF qo'shish bo'limini tanlang."
        )
        return

    document = update.message.document
    if not document:
        await update.message.reply_text("Iltimos, PDF fayl yuboring.")
        return

    filename = document.file_name or "material.pdf"
    lower_name = filename.lower()
    if not (lower_name.endswith(".pdf") or lower_name.endswith(".pptx")):
        await update.message.reply_text("Iltimos, PDF yoki PowerPoint (.pptx) fayl yuboring.")
        return

    tid = context.user_data.get("topic_id")
    if not tid or not topic(tid):
        context.user_data.clear()
        await update.message.reply_text("Mavzu topilmadi. Qaytadan urinib ko'ring.")
        return

    title = filename[:-5] if filename.lower().endswith(".pptx") else (filename[:-4] if filename.lower().endswith(".pdf") else filename)
    replace_id = context.user_data.get("replace_material_id")

    with db() as c:
        if replace_id:
            result = c.execute(
                "UPDATE materials SET title=?, file_id=?, file_name=? WHERE id=? AND topic_id=?",
                (title, document.file_id, filename, replace_id, tid)
            )
            replaced = result.rowcount > 0
            if not replaced:
                context.user_data.clear()
                await update.message.reply_text(
                    "⚠️ Almashtiriladigan material topilmadi. Qaytadan urinib ko'ring."
                )
                return
        else:
            material_type = context.user_data.get("material_type", "presentation")
            c.execute(
                "INSERT INTO materials (topic_id,title,file_id,file_name,material_type) VALUES (?,?,?,?,?)",
                (tid, title, document.file_id, filename, material_type)
            )
            replaced = False

    context.user_data.clear()
    message = "🔄 PDF muvaffaqiyatli almashtirildi!" if replaced else "✅ PDF muvaffaqiyatli saqlandi!"
    await update.message.reply_text(
        f"{message}\n\n📄 {filename}",
        reply_markup=main_menu(True)
    )

async def receive_section_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if not context.user_data.get("waiting_custom_material_files"):
        return

    photo = update.message.photo[-1]
    filename = f"rasm_{update.message.message_id}.jpg"

    with db() as c:
        c.execute(
            "INSERT INTO custom_section_materials "
            "(root_section_id, node_id, material_type, title, text_content, "
            "file_id, file_name, mime_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                context.user_data["custom_material_root_id"],
                context.user_data.get("custom_material_node_id"),
                "file",
                context.user_data["custom_material_title"],
                context.user_data.get("custom_material_description", ""),
                photo.file_id,
                filename,
                "image/jpeg"
            )
        )

    count = context.user_data.get("custom_material_count", 0) + 1
    context.user_data["custom_material_count"] = count

    await update.message.reply_text(
        f"✅ Rasm saqlandi.\n📎 Jami fayllar: {count}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "✅ Yuklashni tugatish",
                callback_data="nav:finishmaterial"
            )
        ]])
    )


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not has_access(user_id):
        await update.message.reply_text("🔒 Kirish uchun avval /start orqali ruxsat so‘rang.")
        return

    if has_teacher_role(user_id):
        context.user_data["profile_step"] = "teacher_name"
        context.user_data.pop("teacher_profile_name", None)
        await update.message.reply_text(
            "👨‍🏫 USTOZ PROFILINI YARATISH / TAHRIRLASH\\n\\n"
            "1/3 — Ism-familiyangizni kiriting.\\n"
            "Bekor qilish: /cancel"
        )
        return

    context.user_data["profile_step"] = "name"
    context.user_data.pop("profile_name", None)
    await update.message.reply_text(
        "👤 TALABA PROFILINI YARATISH / TAHRIRLASH\\n\\n"
        "1/2 — Ism-familiyangizni kiriting.\\n"
        "Masalan: Ali Valiyev\\n\\n"
        "Bekor qilish: /cancel"
    )


async def handle_profile_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get("profile_step")
    teacher_steps = ("teacher_name", "teacher_position", "teacher_degree")

    if step in teacher_steps:
        text = update.message.text.strip()
        if len(text) < 2 or len(text) > 100:
            await update.message.reply_text("Ma'lumot 2–100 belgi oralig'ida bo'lishi kerak.")
            return True

        if step == "teacher_name":
            context.user_data["teacher_profile_name"] = text
            context.user_data["profile_step"] = "teacher_position"
            await update.message.reply_text(
                "2/3 — Lavozimingizni kiriting.\\n"
                "Masalan: Katta o‘qituvchi, dotsent, professor."
            )
            return True

        if step == "teacher_position":
            context.user_data["teacher_profile_position"] = text
            context.user_data["profile_step"] = "teacher_degree"
            await update.message.reply_text(
                "3/3 — Ilmiy darajangizni kiriting.\\n"
                "Masalan: PhD, DSc. Agar bo‘lmasa, «Yo‘q» deb yozing."
            )
            return True

        user = update.effective_user
        full_name = context.user_data.get("teacher_profile_name")
        position = context.user_data.get("teacher_profile_position")
        degree = "" if text.lower() in ("yo‘q", "yo'q", "yoq", "-", "mavjud emas") else text

        if not full_name or not position:
            context.user_data.clear()
            await update.message.reply_text("Qaytadan boshlash uchun /editprofile yuboring.")
            return True

        with db() as c:
            c.execute("""
                INSERT INTO teacher_profiles
                    (telegram_id, full_name, position, academic_degree)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    full_name=excluded.full_name,
                    position=excluded.position,
                    academic_degree=excluded.academic_degree,
                    updated_at=CURRENT_TIMESTAMP
            """, (user.id, full_name, position, degree))

        context.user_data.clear()
        await update.message.reply_text(
            "✅ Ustoz profilingiz saqlandi!\\n\\n"
            f"👤 Ism-familiya: {full_name}\\n"
            f"💼 Lavozim: {position}\\n"
            f"🎓 Ilmiy daraja: {degree or 'Kiritilmagan'}",
            reply_markup=main_menu(
                user.id == ADMIN_ID,
                teacher=has_teacher_role(user.id),
                student=has_student_role(user.id)
            )
        )
        return True

    if step not in ("name", "group"):
        return False

    text = update.message.text.strip()
    if len(text) < 2 or len(text) > 100:
        await update.message.reply_text("Ma'lumot 2–100 belgi oralig'ida bo'lishi kerak.")
        return True

    if step == "name":
        context.user_data["profile_name"] = text
        context.user_data["profile_step"] = "group"
        await update.message.reply_text(
            "2/2 — Guruhingizni kiriting.\\n"
            "Masalan: STK_25.02\\n\\n"
            "Bekor qilish: /cancel"
        )
        return True

    user = update.effective_user
    full_name = context.user_data.get("profile_name")
    if not full_name:
        context.user_data.clear()
        await update.message.reply_text("Qaytadan boshlash uchun /editprofile yuboring.")
        return True

    with db() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                group_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            INSERT INTO students (telegram_id, full_name, group_name)
            VALUES (?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                full_name=excluded.full_name,
                group_name=excluded.group_name
        """, (user.id, full_name, text))
        sid = c.execute(
            "SELECT id FROM students WHERE telegram_id = ?", (user.id,)
        ).fetchone()[0]
        c.execute("""
            CREATE TABLE IF NOT EXISTS student_stats (
                student_id INTEGER PRIMARY KEY,
                completed_topics INTEGER NOT NULL DEFAULT 0,
                tests_completed INTEGER NOT NULL DEFAULT 0,
                total_score INTEGER NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute(
            "INSERT OR IGNORE INTO student_stats (student_id) VALUES (?)",
            (sid,)
        )

    context.user_data.clear()
    await update.message.reply_text(
        "✅ Profil saqlandi!\\n\\n"
        f"🧑 Ism: {full_name}\\n"
        f"🎓 Guruh: {text}\\n\\n"
        "Endi 👤 Profil bo‘limidan ma’lumotlaringizni ko‘rishingiz mumkin.",
        reply_markup=main_menu(
            user.id == ADMIN_ID,
            teacher=has_teacher_role(user.id),
            student=has_student_role(user.id)
        )
    )
    return True


async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()
    admin = user.id == ADMIN_ID

    if not has_access(user.id):
        context.user_data.clear()
        await update.message.reply_text("🔒 Platforma yopiq. Kirish uchun /start ni bosing.")
        return

    # YANGI UY VAZIFASI — MATN KIRITISH BOSQICHLARI
    if context.user_data.get("waiting_hw_title"):
        if not admin:
            context.user_data.clear()
            await update.message.reply_text("⛔ Ruxsat yo‘q.")
            return
        if len(text) < 2 or len(text) > 150:
            await update.message.reply_text("Vazifa nomi 2–150 belgi bo‘lishi kerak.")
            return

        context.user_data["hw_title"] = text
        context.user_data.pop("waiting_hw_title", None)
        context.user_data["waiting_hw_subject"] = True

        with db() as c:
            subjects = c.execute(
                "SELECT id, name FROM subjects ORDER BY name"
            ).fetchall()

        buttons = [
            [InlineKeyboardButton(name, callback_data=f"hw:subject:{sid}")]
            for sid, name in subjects
        ]
        buttons.append([
            InlineKeyboardButton("📚 Umumiy vazifa", callback_data="hw:subject:general")
        ])

        await update.message.reply_text(
            "📚 Vazifa qaysi fanga tegishli?",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    if context.user_data.get("waiting_hw_content"):
        if not admin:
            context.user_data.clear()
            await update.message.reply_text("⛔ Ruxsat yo‘q.")
            return
        if len(text) < 2 or len(text) > 3500:
            await update.message.reply_text("Vazifa matni 2–3500 belgi bo‘lishi kerak.")
            return

        context.user_data["hw_content"] = text
        context.user_data.pop("waiting_hw_content", None)
        context.user_data["waiting_hw_due"] = True

        await update.message.reply_text(
            "📅 Topshirish muddatini YYYY-MM-DD formatida yuboring.\n"
            "Masalan: 2026-11-05",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "Muddat belgilanmagan",
                    callback_data="hw:nodue"
                )
            ]])
        )
        return

    if context.user_data.get("waiting_hw_due"):
        if not admin:
            context.user_data.clear()
            await update.message.reply_text("⛔ Ruxsat yo‘q.")
            return
        try:
            due_date = datetime.strptime(text, "%Y-%m-%d").date().isoformat()
        except ValueError:
            await update.message.reply_text(
                "Sanani YYYY-MM-DD formatida yuboring. Masalan: 2026-11-05"
            )
            return

        title = context.user_data.get("hw_title")
        subject = context.user_data.get("hw_subject")
        content = context.user_data.get("hw_content")

        if not title or not subject or not content:
            context.user_data.clear()
            await update.message.reply_text("Ma’lumotlar yetishmayapti. Qaytadan boshlang.")
            return

        with db() as c:
            c.execute(
                """INSERT INTO homework_posts
                   (title, content, subject_name, due_date, created_by)
                   VALUES (?, ?, ?, ?, ?)""",
                (title, content, subject, due_date, user.id)
            )

        context.user_data.clear()
        await update.message.reply_text(
            "✅ UY VAZIFASI SAQLANDI!\n\n"
            f"📝 {title}\n"
            f"📚 Fan: {subject}\n"
            f"📅 Muddat: {due_date}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Yana vazifa qo‘shish", callback_data="hw:add")],
                [InlineKeyboardButton("📋 Vazifalar ro‘yxati", callback_data="hw:list")],
                [InlineKeyboardButton("🏠 Asosiy menyu", callback_data="nav:home")]
            ])
        )
        return

    if context.user_data.get("waiting_reminder_date"):
        if not admin:
            context.user_data.clear()
            await update.message.reply_text("Faqat administrator uchun.")
            return
        try:
            reminder_date = datetime.strptime(text, "%Y-%m-%d").date().isoformat()
        except ValueError:
            await update.message.reply_text("Sanani YYYY-MM-DD formatida yuboring. Masalan: 2026-10-31")
            return
        kind = context.user_data.pop("waiting_reminder_date")
        context.user_data["waiting_reminder_content"] = kind
        context.user_data["reminder_date"] = reminder_date
        label = "dars jadvali" if kind == "schedule_text" else "uy vazifalari"
        await update.message.reply_text(
            f"{reminder_date} sanasi uchun {label} matnini yuboring. Bekor qilish: /cancel"
        )
        return

    if context.user_data.get("waiting_reminder_content"):
        if not admin:
            context.user_data.clear()
            await update.message.reply_text("Faqat administrator uchun.")
            return
        kind = context.user_data["waiting_reminder_content"]
        reminder_date = context.user_data["reminder_date"]
        if len(text) > 3500:
            await update.message.reply_text("Matn 3500 belgidan oshmasligi kerak.")
            return
        with db() as c:
            row = c.execute(
                "SELECT schedule_text, homework_text FROM daily_reminders WHERE reminder_date = ?",
                (reminder_date,)
            ).fetchone()
            schedule_text, homework_text = row if row else ("", "")
            if kind == "schedule_text":
                schedule_text = text
            else:
                homework_text = text
            c.execute(
                """INSERT INTO daily_reminders
                   (reminder_date, schedule_text, homework_text)
                   VALUES (?, ?, ?)
                   ON CONFLICT(reminder_date) DO UPDATE SET
                   schedule_text = excluded.schedule_text,
                   homework_text = excluded.homework_text,
                   updated_at = CURRENT_TIMESTAMP""",
                (reminder_date, schedule_text, homework_text)
            )
        context.user_data.clear()
        await update.message.reply_text(
            f"Saqlab qo'yildi: {reminder_date}",
            reply_markup=main_menu(True)
        )
        return

    if await handle_profile_input(update, context):
        return

    if context.user_data.get("waiting_teacher_id"):
        if not admin:
            context.user_data.clear()
            await update.message.reply_text("⛔ Ruxsat yo‘q.")
            return
        raw_id = text.strip()
        if not raw_id.isdigit():
            await update.message.reply_text("Telegram ID faqat raqamlardan iborat bo‘lishi kerak. Qayta yuboring yoki /cancel.")
            return
        teacher_id = int(raw_id)
        try:
            with db() as c:
                c.execute(
                    "INSERT INTO teachers (telegram_id) VALUES (?)",
                    (teacher_id,)
                )
            context.user_data.clear()
            await update.message.reply_text(
                f"✅ Ustoz qo‘shildi. Telegram ID: {teacher_id}",
                reply_markup=main_menu(True)
            )
        except sqlite3.IntegrityError:
            context.user_data.clear()
            await update.message.reply_text("ℹ️ Bu ID allaqachon ustoz sifatida qo‘shilgan.")
        return

    if context.user_data.get("waiting_custom_material_title"):
        if not admin:
            context.user_data.clear()
            await update.message.reply_text("⛔ Ruxsat yo‘q.")
            return

        title = text.strip()
        if len(title) < 2 or len(title) > 150:
            await update.message.reply_text("Material nomi 2–150 belgi bo‘lishi kerak.")
            return

        context.user_data["custom_material_title"] = title
        context.user_data.pop("waiting_custom_material_title", None)
        context.user_data["waiting_custom_material_description"] = True
        await update.message.reply_text(
            "📝 Material uchun izoh yuboring. Izoh kerak bo‘lmasa - yuboring."
        )
        return

    if context.user_data.get("waiting_custom_material_description"):
        if not admin:
            context.user_data.clear()
            await update.message.reply_text("⛔ Ruxsat yo‘q.")
            return

        description = "" if text.strip().lower() in ("/skip", "-") else text.strip()
        if len(description) > 3000:
            await update.message.reply_text("Izoh 3000 belgidan oshmasligi kerak.")
            return

        context.user_data["custom_material_description"] = description
        context.user_data.pop("waiting_custom_material_description", None)
        context.user_data["waiting_custom_material_files"] = True
        await update.message.reply_text(
            "📤 Endi PDF, PPTX, DOCX, JPG, PNG, WEBP yoki TXT fayllarini yuboring.\n\n"
            "Bir nechta fayl yuborishingiz mumkin. Yakunlash uchun "
            "«Yuklashni tugatish» tugmasini bosing."
        )
        return

    if context.user_data.get("waiting_custom_node_name"):
        if not admin:
            context.user_data.clear()
            await update.message.reply_text("⛔ Ruxsat yo'q.")
            return

        name = text.strip()
        if len(name) < 2 or len(name) > 100:
            await update.message.reply_text(
                "Bo'lim nomi 2–100 belgi bo'lishi kerak."
            )
            return

        root_id = context.user_data.get("custom_node_root_id")
        rename_id = context.user_data.get("rename_custom_node_id")
        parent_id = context.user_data.get("custom_node_parent_id")

        with db() as c:
            if rename_id is not None:
                result = c.execute(
                    "UPDATE custom_section_nodes SET name=? "
                    "WHERE id=? AND root_section_id=?",
                    (name, rename_id, root_id)
                )
                if result.rowcount == 0:
                    context.user_data.clear()
                    await update.message.reply_text(
                        "⚠️ Tahrirlanadigan papka topilmadi.",
                        reply_markup=main_menu(True)
                    )
                    return
            else:
                c.execute(
                    "INSERT INTO custom_section_nodes "
                    "(root_section_id, parent_id, name) VALUES (?, ?, ?)",
                    (root_id, parent_id, name)
                )

        context.user_data.clear()

        if rename_id is not None:
            await update.message.reply_text(
                f"✅ Papka nomi yangilandi: {name}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "⬅️ Papkaga qaytish",
                        callback_data=f"nav:node:{root_id}:{rename_id}"
                    )
                ]])
            )
        else:
            await update.message.reply_text(
                f"✅ Ichki bo'lim yaratildi: {name}",
                reply_markup=main_menu(True)
            )
        return

    if context.user_data.get("waiting_section_name"):
        if not admin:
            context.user_data.clear()
            await update.message.reply_text("⛔ Ruxsat yo‘q.")
            return
        name = text.strip()
        if len(name) < 2 or len(name) > 100:
            await update.message.reply_text("Bo‘lim nomi 2–100 belgi bo‘lishi kerak.")
            return
        rename_id = context.user_data.get("rename_section_id")
        try:
            with db() as c:
                if rename_id:
                    c.execute("UPDATE custom_sections SET name = ? WHERE id = ?", (name, rename_id))
                else:
                    show_students = context.user_data.get("section_show_students", 1)
                    show_teachers = context.user_data.get("section_show_teachers", 1)
                    c.execute(
                        """INSERT INTO custom_sections
                           (name, show_students, show_teachers)
                           VALUES (?, ?, ?)""",
                        (name, show_students, show_teachers)
                    )
            context.user_data.clear()
            if rename_id:
                await update.message.reply_text(f"✅ Bo‘lim nomi o‘zgartirildi: {name}", reply_markup=main_menu(True))
            else:
                await update.message.reply_text(f"✅ Bo‘lim qo‘shildi: {name}", reply_markup=main_menu(True))
        except sqlite3.IntegrityError:
            await update.message.reply_text("Bu nomdagi bo‘lim mavjud. Boshqa nom kiriting.")
        return

    if context.user_data.get("waiting_topics_batch"):
        if not admin:
            context.user_data.clear()
            await update.message.reply_text("⛔ Ruxsat yo'q.")
            return

        sid = context.user_data.get("batch_subject_id")
        if not sid or not subject(sid):
            context.user_data.clear()
            await update.message.reply_text(
                "Fan topilmadi. Qaytadan urinib ko'ring."
            )
            return

        names = [line.strip() for line in text.splitlines() if line.strip()]
        if not names:
            await update.message.reply_text(
                "Mavzular topilmadi. Har bir mavzuni yangi qatordan yozing."
            )
            return

        added = []
        skipped = []
        invalid = []

        with db() as c:
            for name in names:
                if len(name) < 2 or len(name) > 200:
                    invalid.append(name)
                    continue
                try:
                    c.execute(
                        "INSERT INTO topics (subject_id, name) VALUES (?, ?)",
                        (sid, name)
                    )
                    added.append(name)
                except sqlite3.IntegrityError:
                    skipped.append(name)

        context.user_data.clear()
        result = [
            "📚 KTP mavzulari qayta ishlandi.",
            f"✅ Yangi qo'shildi: {len(added)}",
            f"↩️ Avval mavjud edi: {len(skipped)}",
            f"⚠️ Noto'g'ri uzunlik: {len(invalid)}",
        ]
        if added:
            result.append("\nYangi mavzular:\n" + "\n".join(
                f"• {name}" for name in added[:30]
            ))
        if skipped:
            result.append("\nAvval mavjud mavzular:\n" + "\n".join(
                f"• {name}" for name in skipped[:15]
            ))
        if invalid:
            result.append("\nTekshirish kerak:\n" + "\n".join(
                f"• {name[:80]}" for name in invalid[:10]
            ))

        await update.message.reply_text(
            "\n".join(result),
            reply_markup=main_menu(True)
        )
        return

    if context.user_data.get("waiting_pdf_name"):
        if not admin:
            context.user_data.clear()
            await update.message.reply_text("⛔ Ruxsat yo'q.")
            return

        mid = context.user_data.get("rename_material_id")
        new_title = text.strip()
        if not new_title or len(new_title) > 200:
            await update.message.reply_text(
                "Nom 1–200 belgi oralig'ida bo'lishi kerak."
            )
            return

        with db() as c:
            result = c.execute(
                "UPDATE materials SET title=? WHERE id=?",
                (new_title, mid)
            )

        if result.rowcount == 0:
            context.user_data.clear()
            await update.message.reply_text("Material topilmadi.")
            return

        context.user_data.clear()
        await update.message.reply_text(
            f"✅ PDF nomi o'zgartirildi: {new_title}",
            reply_markup=main_menu(True)
        )
        return

    if context.user_data.get("waiting_topic_name"):
        if not admin:
            context.user_data.clear()
            await update.message.reply_text("⛔ Ruxsat yo'q.")
            return

        tid = context.user_data.get("rename_topic_id")
        if len(text.strip()) < 2 or len(text.strip()) > 200:
            await update.message.reply_text(
                "Mavzu nomi 2–200 belgi bo'lishi kerak."
            )
            return

        try:
            with db() as c:
                result = c.execute(
                    "UPDATE topics SET name=? WHERE id=?",
                    (text.strip(), tid)
                )
                if result.rowcount == 0:
                    context.user_data.clear()
                    await update.message.reply_text("Mavzu topilmadi.")
                    return

            context.user_data.clear()
            await update.message.reply_text(
                f"✅ Mavzu nomi o'zgartirildi: {text.strip()}",
                reply_markup=main_menu(True)
            )
        except sqlite3.IntegrityError:
            await update.message.reply_text(
                "Bu nomdagi mavzu allaqachon mavjud. Boshqa nom kiriting."
            )
        return

    if context.user_data.get("waiting_subject"):
        if not admin:
            context.user_data.clear()
            await update.message.reply_text("⛔ Ruxsat yo'q.")
            return
        sid = context.user_data["subject_id"]
        if len(text) < 2 or len(text) > 200:
            await update.message.reply_text("Mavzu nomi 2–200 belgi bo'lishi kerak.")
            return
        try:
            with db() as c:
                c.execute(
                    "INSERT INTO topics (subject_id,name) VALUES (?,?)",
                    (sid, text)
                )
            context.user_data.clear()
            await update.message.reply_text(
                f"✅ Mavzu qo'shildi: {text}", reply_markup=main_menu(True)
            )
        except sqlite3.IntegrityError:
            context.user_data.clear()
            await update.message.reply_text(
                "Bu mavzu avval qo'shilgan.", reply_markup=main_menu(True)
            )
        return

    if context.user_data.get("waiting_subject_name"):
        if not admin:
            context.user_data.clear()
            await update.message.reply_text("⛔ Ruxsat yo'q.")
            return

        if len(text) < 2 or len(text) > 100:
            await update.message.reply_text(
                "Fan nomi 2–100 belgi bo'lishi kerak."
            )
            return

        rename_id = context.user_data.get("rename_subject_id")

        try:
            with db() as c:
                if rename_id is not None:
                    result = c.execute(
                        "UPDATE subjects SET name=? WHERE id=?",
                        (text, rename_id)
                    )
                    if result.rowcount == 0:
                        context.user_data.clear()
                        await update.message.reply_text(
                            "⚠️ Tahrirlanadigan fan topilmadi.",
                            reply_markup=main_menu(True)
                        )
                        return
                else:
                    c.execute(
                        "INSERT INTO subjects (name) VALUES (?)",
                        (text,)
                    )

            context.user_data.clear()

            if rename_id is not None:
                message = f"✅ Fan nomi yangilandi: {text}"
            else:
                message = f"✅ Fan qo'shildi: {text}"

            await update.message.reply_text(
                message,
                reply_markup=main_menu(True)
            )

        except sqlite3.IntegrityError:
            context.user_data.clear()
            await update.message.reply_text(
                "Bu nomdagi fan avval mavjud.",
                reply_markup=main_menu(True)
            )

        return

    if text in ("📊 Prezentatsiyalar", "📝 Mustaqil ish"):
        with db() as c:
            teacher = c.execute(
                "SELECT 1 FROM teachers WHERE telegram_id=?",
                (update.effective_user.id,)
            ).fetchone()
            assigned = c.execute(
                "SELECT s.id, s.name FROM subjects s "
                "JOIN teacher_subjects ts ON ts.subject_id=s.id "
                "WHERE ts.teacher_id=? ORDER BY s.name",
                (update.effective_user.id,)
            ).fetchall()

        if not teacher or admin:
            await update.message.reply_text("⛔ Bu bo‘lim faqat ustozlar uchun.")
            return

        if not assigned:
            await update.message.reply_text("Sizga hali fan biriktirilmagan.")
            return

        kind = "presentation" if text == "📊 Prezentatsiyalar" else "independent"
        buttons = [
            [InlineKeyboardButton(
                f"📚 {name}",
                callback_data=f"teacher_subject:{kind}:{sid}"
            )]
            for sid, name in assigned
        ]
        await update.message.reply_text(
            f"{text} — fan tanlang:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    if text == "📚 Fanlar":
        await show_subjects(update.message)
    elif text == "➕ Fan qo'shish":
        if not admin:
            await update.message.reply_text("⛔ Ruxsat yo'q.")
            return
        context.user_data.clear()
        context.user_data["waiting_subject_name"] = True
        await update.message.reply_text("Yangi fan nomini yuboring. Bekor qilish: /cancel")
    elif text == "📖 Mavzu qo'shish":
        if not admin:
            await update.message.reply_text("⛔ Ruxsat yo'q.")
            return
        await show_subjects(update.message)
    elif text == "📄 PDF qo'shish":
        if not admin:
            await update.message.reply_text("⛔ Ruxsat yo'q.")
            return
        await show_subjects(update.message, "pdf_subject")
    elif text.startswith("📦 ") and text != "📦 Bo‘limlarni boshqarish":
        section_name = text[2:].strip()
        with db() as c:
            section = c.execute(
                "SELECT name FROM custom_sections "
                "WHERE name = ? AND is_visible = 1",
                (section_name,)
            ).fetchone()
        if section:
            await update.message.reply_text(
                f"📦 {section_name}\\n\\n"
                "Bo‘lim yaratildi. Hozircha bu bo‘limga materiallar ulanmagan."
            )
    elif text == "📦 Bo‘limlarni boshqarish":
        if not admin:
            await update.message.reply_text("⛔ Ruxsat yo‘q.")
            return
        keyboard = ReplyKeyboardMarkup(
            [["➕ Bo‘lim qo‘shish", "📋 Bo‘limlar ro‘yxati"], ["⬅️ Asosiy menyu"]],
            resize_keyboard=True
        )
        await update.message.reply_text("📦 BO‘LIMLARNI BOSHQARISH", reply_markup=keyboard)
    elif text == "➕ Bo‘lim qo‘shish":
        if not admin:
            await update.message.reply_text("⛔ Ruxsat yo‘q.")
            return
        context.user_data.clear()
        context.user_data["waiting_section_name"] = True
        await update.message.reply_text("Yangi bo‘lim nomini yuboring. Bekor qilish: /cancel")
    elif text == "📋 Bo‘limlar ro‘yxati":
        if not admin:
            await update.message.reply_text("⛔ Ruxsat yo‘q.")
            return
        with db() as c:
            items = c.execute("SELECT id, name, is_visible, show_students, show_teachers FROM custom_sections ORDER BY position, id").fetchall()
        if not items:
            await update.message.reply_text("Hozircha bo‘limlar yo‘q.")
        else:
            for i, name, visible, students, teachers in items:
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✏️ Nomini o‘zgartirish", callback_data=f"renamesection:{i}"),
                        InlineKeyboardButton("👁 Ko‘rinishni almashtirish", callback_data=f"togglesection:{i}")
                    ],
                    [
                        InlineKeyboardButton("👨‍🎓 Talabalar: " + ("ha" if students else "yo‘q"), callback_data=f"togglestudents:{i}"),
                        InlineKeyboardButton("👨‍🏫 Ustozlar: " + ("ha" if teachers else "yo‘q"), callback_data=f"toggleteachers:{i}")
                    ],
                    [InlineKeyboardButton("🗑 O‘chirish", callback_data=f"deletesection:{i}")]
                ])
                await update.message.reply_text(
                    f"📦 {name}\nHolati: {'ko‘rinadi' if visible else 'yashirilgan'}",
                    reply_markup=keyboard
                )
    elif text == "⬅️ Asosiy menyu":
        await update.message.reply_text("Asosiy menyu.", reply_markup=main_menu(admin))
    elif text == "👨‍🏫 Ustozlarni boshqarish":
        if not admin:
            await update.message.reply_text("⛔ Faqat administrator uchun.")
            return
        keyboard = ReplyKeyboardMarkup(
            [["➕ Ustoz qo‘shish", "📋 Ustozlar ro‘yxati"],
             ["🎓 Fan biriktirish"],
             ["⬅️ Asosiy menyu"]],
            resize_keyboard=True
        )
        await update.message.reply_text(
            "👨‍🏫 USTOZLARNI BOSHQARISH",
            reply_markup=keyboard
        )
    elif text == "➕ Ustoz qo‘shish":
        if not admin:
            await update.message.reply_text("⛔ Faqat administrator uchun.")
            return
        context.user_data.clear()
        context.user_data["waiting_teacher_id"] = True
        await update.message.reply_text(
            "Ustozning Telegram ID raqamini yuboring.\\n"
            "Bekor qilish: /cancel"
        )
    elif text == "🎓 Fan biriktirish":
        if not admin:
            await update.message.reply_text("⛔ Faqat administrator uchun.")
            return
        with db() as c:
            teacher_rows = c.execute(
                "SELECT telegram_id FROM teachers ORDER BY id"
            ).fetchall()
        if not teacher_rows:
            await update.message.reply_text("Avval ustoz qo‘shing.")
            return
        buttons = [[InlineKeyboardButton(
            f"👨‍🏫 {row[0]}", callback_data=f"assignteacher:{row[0]}"
        )] for row in teacher_rows]
        await update.message.reply_text(
            "Ustozni tanlang:", reply_markup=InlineKeyboardMarkup(buttons)
        )
    elif text == "📋 Ustozlar ro‘yxati":
        if not admin:
            await update.message.reply_text("⛔ Faqat administrator uchun.")
            return
        with db() as c:
            teachers = c.execute(
                "SELECT telegram_id FROM teachers ORDER BY id"
            ).fetchall()
        if not teachers:
            await update.message.reply_text("Hozircha ustozlar qo‘shilmagan.")
        else:
            for row in teachers:
                teacher_id = row[0]
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "❌ Ruxsatni bekor qilish",
                        callback_data=f"removeteacher:{teacher_id}"
                    )
                ]])
                await update.message.reply_text(
                    f"👨‍🏫 Ustoz ID: {teacher_id}",
                    reply_markup=keyboard
                )
    elif text == "👨‍🏫 Ustoz paneli":
        with db() as c:
            teacher = c.execute(
                "SELECT 1 FROM teachers WHERE telegram_id = ?",
                (update.effective_user.id,)
            ).fetchone()

        if not teacher or admin:
            await update.message.reply_text("⛔ Bu panel faqat ro‘yxatdagi ustozlar uchun.")
            return

        keyboard = ReplyKeyboardMarkup(
            [["📊 Prezentatsiyalar"], ["📝 Mustaqil ish"],
             ["⬅️ Asosiy menyu"]],
            resize_keyboard=True
        )
        await update.message.reply_text(
            "👨‍🏫 USTOZ PANELI\\n\\n"
            "Kerakli bo‘limni tanlang:",
            reply_markup=keyboard
        )
    elif text == "⬅️ Asosiy menyu":
        with db() as c:
            teacher = c.execute(
                "SELECT 1 FROM teachers WHERE telegram_id = ?",
                (update.effective_user.id,)
            ).fetchone() is not None
        student = False
        with db() as c:
            student = c.execute(
                "SELECT 1 FROM students WHERE telegram_id = ?",
                (update.effective_user.id,)
            ).fetchone() is not None

        await update.message.reply_text(
            "🦷 MedStudy | UBS — asosiy menyu",
            reply_markup=main_menu(admin, teacher and not admin, student)
        )
    elif text == "🛠 Admin panel":
        if not admin:
            await update.message.reply_text("⛔ Ruxsat yo'q.")
            return
        await update.message.reply_text(
            "🛠 ADMIN PANEL\n\n"
            "➕ Fan qo'shish\n📖 Mavzu qo'shish\n📄 PDF qo'shish",
            reply_markup=main_menu(True)
        )
    elif text == "👤 Profil":
        if has_teacher_role(user.id) and user.id != ADMIN_ID:
            profile_text = teacher_profile_text(user.id)
        else:
            with db() as c:
                c.execute("""
                    CREATE TABLE IF NOT EXISTS students (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        telegram_id INTEGER UNIQUE NOT NULL,
                        full_name TEXT NOT NULL,
                        group_name TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                c.execute("""
                    CREATE TABLE IF NOT EXISTS student_stats (
                        student_id INTEGER PRIMARY KEY,
                        completed_topics INTEGER NOT NULL DEFAULT 0,
                        tests_completed INTEGER NOT NULL DEFAULT 0,
                        total_score INTEGER NOT NULL DEFAULT 0,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                student = c.execute(
                    "SELECT id, full_name, group_name FROM students WHERE telegram_id=?",
                    (user.id,)
                ).fetchone()

                if student:
                    sid, full_name, group_name = student
                    c.execute(
                        "INSERT OR IGNORE INTO student_stats (student_id) VALUES (?)",
                        (sid,)
                    )
                    stats = c.execute(
                        "SELECT completed_topics, tests_completed, total_score "
                        "FROM student_stats WHERE student_id=?",
                        (sid,)
                    ).fetchone()
                    completed, tests, score = stats or (0, 0, 0)
                    profile_text = (
                        "👤 TALABA PROFILI\\n\\n"
                        f"🧑 Ism: {full_name}\\n"
                        f"🎓 Guruh: {group_name or 'Kiritilmagan'}\\n"
                        f"🆔 Telegram ID: {user.id}\\n"
                        f"📚 Tugatilgan mavzular: {completed}\\n"
                        f"📝 Ishlangan testlar: {tests}\\n"
                        f"⭐ Umumiy ball: {score}\\n\\n"
                        "Profilni tahrirlash uchun /editprofile buyrug‘ini yuboring."
                    )
                else:
                    profile_text = (
                        "👤 TALABA PROFILI\\n\\n"
                        "Profilingiz hali yaratilmagan.\\n"
                        "Ism-familiya va guruhingizni kiritish uchun "
                        "/editprofile buyrug‘ini yuboring."
                    )

        profile_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "📋 ID ni nusxalash",
                callback_data=f"copyid:{user.id}"
            )]
        ])
        await update.message.reply_text(
            profile_text,
            reply_markup=profile_keyboard
        )
        await update.message.reply_text(
            "Asosiy menyu:",
            reply_markup=main_menu(admin)
        )

    elif text == "ℹ️ Bot haqida":
        await update.message.reply_text(
            "🦷 MedStudy | UBS\nTalabalar uchun o'quv platformasi."
        )
    else:
        await update.message.reply_text("Kerakli bo'limni menyudan tanlang.")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    if not has_access(update.effective_user.id):
        await update.message.reply_text("🔒 Platforma yopiq. Kirish uchun /start ni bosing.")
        return
    await update.message.reply_text(
        "Amal bekor qilindi.",
        reply_markup=main_menu(
            admin=update.effective_user.id == ADMIN_ID,
            teacher=has_teacher_role(update.effective_user.id),
            student=has_student_role(update.effective_user.id)
        )
    )


async def send_daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    tz = timezone(timedelta(hours=5))
    tomorrow = (datetime.now(tz).date() + timedelta(days=1)).isoformat()

    with db() as c:
        row = c.execute(
            "SELECT schedule_text, homework_text FROM daily_reminders WHERE reminder_date = ?",
            (tomorrow,)
        ).fetchone()

        # Faqat talaba bo‘lgan, o‘qituvchi bo‘lmagan akkauntlar
        recipients = {
            r[0] for r in c.execute(
                """
                SELECT s.telegram_id
                FROM students s
                WHERE s.telegram_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM teachers t
                      WHERE t.telegram_id = s.telegram_id
                  )
                """
            ).fetchall()
        }

    if not row or not (row[0].strip() or row[1].strip()):
        logging.info("Ertangi sana uchun eslatma kiritilmagan: %s", tomorrow)
        return

    schedule_text, homework_text = row
    message = f"📅 ERTANGI DARS — {tomorrow}\n\n"
    message += "🕘 Dars jadvali:\n" + (schedule_text.strip() or "Kiritilmagan")
    message += "\n\n📝 Uy vazifalari:\n" + (homework_text.strip() or "Kiritilmagan")

    for chat_id in recipients:
        try:
            await context.bot.send_message(chat_id=chat_id, text=message)
        except Exception:
            logging.warning("Eslatma yuborilmadi. Telegram ID: %s", chat_id)



def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN topilmadi. Tokenni qayta kiriting.")
    init_db()
    app = Application.builder().token(TOKEN).build()
    if app.job_queue is None:
        raise RuntimeError(
            "JobQueue mavjud emas. Termuxda: pip install \"python-telegram-bot[job-queue]==22.8\""
        )
    # Avtomatik dars jadvali va uy vazifasi eslatmalari o‘chirildi.
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("editprofile", profile_command))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.Document.PDF | filters.Document.ALL, receive_pdf))
    app.add_handler(MessageHandler(filters.PHOTO, receive_section_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler))
    print("MedStudy | UBS ishga tushdi!")
    app.run_polling()


if __name__ == "__main__":
    main()
