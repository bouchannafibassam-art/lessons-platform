#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import os
import re
from werkzeug.utils import secure_filename
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, g, flash, send_from_directory
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "lessons.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")

ALLOWED_VIDEO_EXT = {"mp4", "webm", "ogg", "mov"}
MAX_CONTENT_LENGTH = 200 * 1024 * 1024

ADMIN_PASSWORD = "admin123"

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
    static_url_path="/static",
)

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "dev-secret-change-me"
)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ---------------------------------------------------------------
# قاعدة البيانات
# ---------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)

    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS levels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            stage TEXT NOT NULL,
            order_num INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            FOREIGN KEY (level_id)
            REFERENCES levels(id)
            ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            video_url TEXT,
            video_file TEXT,
            FOREIGN KEY (subject_id)
            REFERENCES subjects(id)
            ON DELETE CASCADE
        );
        """
    )

    db.commit()

    cols = [
        row[1]
        for row in db.execute(
            "PRAGMA table_info(lessons)"
        ).fetchall()
    ]

    if "video_file" not in cols:
        db.execute(
            "ALTER TABLE lessons ADD COLUMN video_file TEXT"
        )
        db.commit()

    if db.execute(
        "SELECT COUNT(*) FROM levels"
    ).fetchone()[0] == 0:
        seed(db)

    db.close()


LEVELS_SEED = [
    ("الابتدائي", "السنة الأولى ابتدائي", 1),
    ("الابتدائي", "السنة الثانية ابتدائي", 2),
    ("الابتدائي", "السنة الثالثة ابتدائي", 3),
    ("الابتدائي", "السنة الرابعة ابتدائي", 4),
    ("الابتدائي", "السنة الخامسة ابتدائي", 5),
    ("الابتدائي", "السنة السادسة ابتدائي", 6),

    ("الإعدادي", "الأولى إعدادي", 7),
    ("الإعدادي", "الثانية إعدادي", 8),
    ("الإعدادي", "الثالثة إعدادي", 9),

    ("الثانوي التأهيلي", "الجذع المشترك", 10),
    ("الثانوي التأهيلي", "الأولى باكالوريا", 11),
    ("الثانوي التأهيلي", "الثانية باكالوريا", 12),
]

SUBJECTS_SEED = [
    "الرياضيات",
    "اللغة العربية",
    "اللغة الفرنسية",
    "العلوم",
    "الاجتماعيات",
    "التربية الإسلامية",
    "اللغة الإنجليزية"
]

SAMPLE_LESSON = {
    "title": "درس تجريبي — عدّل أو احذف هذا",
    "content": (
        "هاد الدرس مثال بسيط باش تشوف شكل العرض. "
        "دخل من /admin وزيد الدروس الحقيقية ديالك هنا، "
        "بالعنوان والمحتوى وفيديو."
    ),
    "video_url": "",
}


def seed(db):
    for stage, name, order_num in LEVELS_SEED:

        cur = db.execute(
            """
            INSERT INTO levels
            (name, stage, order_num)
            VALUES (?, ?, ?)
            """,
            (name, stage, order_num)
        )

        level_id = cur.lastrowid

        for subj in SUBJECTS_SEED:

            cur2 = db.execute(
                """
                INSERT INTO subjects
                (level_id, name)
                VALUES (?, ?)
                """,
                (level_id, subj)
            )

            subject_id = cur2.lastrowid

            db.execute(
                """
                INSERT INTO lessons
                (subject_id, title, content,
                 video_url, video_file)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    subject_id,
                    SAMPLE_LESSON["title"],
                    SAMPLE_LESSON["content"],
                    SAMPLE_LESSON["video_url"],
                    None
                )
            )

    db.commit()


# ---------------------------------------------------------------
# الفيديو
# ---------------------------------------------------------------

def allowed_video_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_VIDEO_EXT
    )


def youtube_embed_url(url):

    if not url:
        return None

    patterns = [
        r"youtu\.be/([A-Za-z0-9_-]{6,})",
        r"youtube\.com/watch\?v=([A-Za-z0-9_-]{6,})",
        r"youtube\.com/embed/([A-Za-z0-9_-]{6,})",
        r"youtube\.com/shorts/([A-Za-z0-9_-]{6,})",
    ]

    for pat in patterns:

        m = re.search(pat, url)

        if m:
            return (
                "https://www.youtube.com/embed/"
                + m.group(1)
            )

    return None


app.jinja_env.filters["youtube_embed"] = youtube_embed_url


def save_uploaded_video(file_storage):

    if not file_storage or file_storage.filename == "":
        return None

    if not allowed_video_file(file_storage.filename):

        flash(
            "صيغة الفيديو ماشي مدعومة. "
            "المسموح: mp4, webm, ogg, mov"
        )

        return None

    filename = secure_filename(
        file_storage.filename
    )

    base, ext = os.path.splitext(filename)

    counter = 1
    final_name = filename

    while os.path.exists(
        os.path.join(
            app.config["UPLOAD_FOLDER"],
            final_name
        )
    ):

        final_name = (
            f"{base}_{counter}{ext}"
        )

        counter += 1

    file_storage.save(
        os.path.join(
            app.config["UPLOAD_FOLDER"],
            final_name
        )
    )

    return final_name


def delete_uploaded_video(filename):

    if not filename:
        return

    path = os.path.join(
        app.config["UPLOAD_FOLDER"],
        filename
    )

    if os.path.exists(path):
        os.remove(path)


# ---------------------------------------------------------------
# الصفحات العامة
# ---------------------------------------------------------------

@app.route("/")
def index():

    db = get_db()

    levels = db.execute(
        """
        SELECT * FROM levels
        ORDER BY order_num
        """
    ).fetchall()

    stages = {}

    for lvl in levels:
        stages.setdefault(
            lvl["stage"],
            []
        ).append(lvl)

    return render_template(
        "index.html",
        stages=stages
    )


@app.route("/level/<int:level_id>")
def level_page(level_id):

    db = get_db()

    level = db.execute(
        "SELECT * FROM levels WHERE id=?",
        (level_id,)
    ).fetchone()

    if level is None:
        return "المستوى ماشي موجود", 404

    subjects = db.execute(
        """
        SELECT * FROM subjects
        WHERE level_id=?
        ORDER BY name
        """,
        (level_id,)
    ).fetchall()

    return render_template(
        "level.html",
        level=level,
        subjects=subjects
    )


@app.route("/subject/<int:subject_id>")
def subject_page(subject_id):

    db = get_db()

    subject = db.execute(
        """
        SELECT subjects.*,
               levels.name AS level_name,
               levels.id AS level_id
        FROM subjects
        JOIN levels
        ON subjects.level_id = levels.id
        WHERE subjects.id=?
        """,
        (subject_id,)
    ).fetchone()

    if subject is None:
        return "المادة ماشي موجودة", 404

    lessons = db.execute(
        """
        SELECT * FROM lessons
        WHERE subject_id=?
        ORDER BY id
        """,
        (subject_id,)
    ).fetchall()

    return render_template(
        "subject.html",
        subject=subject,
        lessons=lessons
    )


@app.route("/lesson/<int:lesson_id>")
def lesson_page(lesson_id):

    db = get_db()

    lesson = db.execute(
        """
        SELECT lessons.*,
               subjects.name AS subject_name,
               subjects.id AS subject_id,
               levels.name AS level_name,
               levels.id AS level_id
        FROM lessons
        JOIN subjects
        ON lessons.subject_id = subjects.id
        JOIN levels
        ON subjects.level_id = levels.id
        WHERE lessons.id=?
        """,
        (lesson_id,)
    ).fetchone()

    if lesson is None:
        return "الدرس ماشي موجود", 404

    return render_template(
        "lesson.html",
        lesson=lesson
    )


@app.route("/search")
def search():

    q = request.args.get(
        "q",
        ""
    ).strip()

    db = get_db()

    results = []

    if q:

        results = db.execute(
            """
            SELECT lessons.*,
                   subjects.name AS subject_name,
                   levels.name AS level_name
            FROM lessons
            JOIN subjects
            ON lessons.subject_id = subjects.id
            JOIN levels
            ON subjects.level_id = levels.id
            WHERE lessons.title LIKE ?
               OR lessons.content LIKE ?
            ORDER BY levels.order_num
            """,
            (
                f"%{q}%",
                f"%{q}%"
            )
        ).fetchall()

    return render_template(
        "search.html",
        q=q,
        results=results
    )


# ---------------------------------------------------------------
# Monetag sw.js
# ---------------------------------------------------------------

@app.route("/sw.js")
def monetag_sw():
    return send_from_directory(
        BASE_DIR,
        "sw.js"
    )


# ---------------------------------------------------------------
# الفيديوهات المرفوعة
# ---------------------------------------------------------------

@app.route("/uploads/<path:filename>")
def uploaded_video(filename):

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        filename
    )


# ---------------------------------------------------------------
# Admin
# ---------------------------------------------------------------

def is_logged_in():
    return session.get(
        "is_admin",
        False
    )


@app.route(
    "/admin/login",
    methods=["GET", "POST"]
)
def admin_login():

    if request.method == "POST":

        if request.form.get(
            "password"
        ) == ADMIN_PASSWORD:

            session["is_admin"] = True

            return redirect(
                url_for(
                    "admin_dashboard"
                )
            )

        flash(
            "كلمة السر غالطة."
        )

    return render_template(
        "login.html"
    )


@app.route("/admin/logout")
def admin_logout():

    session.pop(
        "is_admin",
        None
    )

    return redirect(
        url_for("index")
    )


@app.route("/admin")
def admin_dashboard():

    if not is_logged_in():
        return redirect(
            url_for("admin_login")
        )

    db = get_db()

    levels = db.execute(
        """
        SELECT * FROM levels
        ORDER BY order_num
        """
    ).fetchall()

    subjects_by_level = {}

    for lvl in levels:

        subjects_by_level[lvl["id"]] = db.execute(
            """
            SELECT * FROM subjects
            WHERE level_id=?
            ORDER BY name
            """,
            (lvl["id"],)
        ).fetchall()

    return render_template(
        "admin.html",
        levels=levels,
        subjects_by_level=subjects_by_level
    )


@app.route(
    "/admin/subject/<int:subject_id>"
)
def admin_subject(subject_id):

    if not is_logged_in():
        return redirect(
            url_for("admin_login")
        )

    db = get_db()

    subject = db.execute(
        "SELECT * FROM subjects WHERE id=?",
        (subject_id,)
    ).fetchone()

    lessons = db.execute(
        """
        SELECT * FROM lessons
        WHERE subject_id=?
        ORDER BY id
        """,
        (subject_id,)
    ).fetchall()

    return render_template(
        "admin_subject.html",
        subject=subject,
        lessons=lessons
    )


@app.route(
    "/admin/lesson/add/<int:subject_id>",
    methods=["POST"]
)
def admin_add_lesson(subject_id):

    if not is_logged_in():
        return redirect(
            url_for("admin_login")
        )

    db = get_db()

    video_file = save_uploaded_video(
        request.files.get("video_file")
    )

    video_url = request.form.get(
        "video_url",
        ""
    ).strip()

    db.execute(
        """
        INSERT INTO lessons
        (subject_id, title, content,
         video_url, video_file)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            subject_id,
            request.form["title"],
            request.form["content"],
            video_url,
            video_file
        )
    )

    db.commit()

    flash(
        "تزاد الدرس بنجاح."
    )

    return redirect(
        url_for(
            "admin_subject",
            subject_id=subject_id
        )
    )


@app.route(
    "/admin/lesson/edit/<int:lesson_id>",
    methods=["GET", "POST"]
)
def admin_edit_lesson(lesson_id):

    if not is_logged_in():
        return redirect(
            url_for("admin_login")
        )

    db = get_db()

    lesson = db.execute(
        "SELECT * FROM lessons WHERE id=?",
        (lesson_id,)
    ).fetchone()

    if lesson is None:
        return "الدرس ماشي موجود", 404

    if request.method == "POST":

        video_url = request.form.get(
            "video_url",
            ""
        ).strip()

        new_video_file = request.files.get(
            "video_file"
        )

        video_file = lesson["video_file"]

        if request.form.get(
            "remove_video_file"
        ) == "1":

            delete_uploaded_video(
                lesson["video_file"]
            )

            video_file = None

        if (
            new_video_file
            and new_video_file.filename
        ):

            delete_uploaded_video(
                video_file
            )

            video_file = save_uploaded_video(
                new_video_file
            )

        db.execute(
            """
            UPDATE lessons
            SET title=?,
                content=?,
                video_url=?,
                video_file=?
            WHERE id=?
            """,
            (
                request.form["title"],
                request.form["content"],
                video_url,
                video_file,
                lesson_id
            )
        )

        db.commit()

        flash(
            "تبدل الدرس بنجاح."
        )

        return redirect(
            url_for(
                "admin_subject",
                subject_id=lesson["subject_id"]
            )
        )

    return render_template(
        "admin_edit.html",
        lesson=lesson
    )


@app.route(
    "/admin/lesson/delete/<int:lesson_id>",
    methods=["POST"]
)
def admin_delete_lesson(lesson_id):

    if not is_logged_in():
        return redirect(
            url_for("admin_login")
        )

    db = get_db()

    lesson = db.execute(
        "SELECT * FROM lessons WHERE id=?",
        (lesson_id,)
    ).fetchone()

    if lesson is None:
        return "الدرس ماشي موجود", 404

    delete_uploaded_video(
        lesson["video_file"]
    )

    db.execute(
        "DELETE FROM lessons WHERE id=?",
        (lesson_id,)
    )

    db.commit()

    flash(
        "تحذف الدرس."
    )

    return redirect(
        url_for(
            "admin_subject",
            subject_id=lesson["subject_id"]
        )
    )


# ---------------------------------------------------------------
# تشغيل التطبيق
# ---------------------------------------------------------------

init_db()


if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    debug_mode = (
        os.environ.get(
            "FLASK_DEBUG",
            "1"
        ) == "1"
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=debug_mode
    )
