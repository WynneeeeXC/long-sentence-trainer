# -*- coding: utf-8 -*-
"""SQLite 数据层：句子 + 复习记录 + 必背短语，兼容旧版库的平滑迁移。"""
import json
import sqlite3

import config


def get_conn():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """建表 + 旧库补列迁移 + 旧考点名迁移。"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS sentences (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            stem            TEXT NOT NULL,
            source          TEXT DEFAULT '手动输入',
            analysis        TEXT,
            structure       TEXT,
            exam_points     TEXT,
            seg_translation TEXT,
            full_translation TEXT,
            tips            TEXT,
            note            TEXT DEFAULT '',
            difficulty      INTEGER DEFAULT 3,
            created_at      TIMESTAMP DEFAULT (datetime('now','localtime')),
            updated_at      TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            sentence_id     INTEGER NOT NULL REFERENCES sentences(id) ON DELETE CASCADE,
            user_translation TEXT,
            self_rating     TEXT,
            reviewed_at     TIMESTAMP DEFAULT (datetime('now','localtime'))
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS phrases (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            sentence_id INTEGER REFERENCES sentences(id) ON DELETE SET NULL,
            phrase      TEXT NOT NULL,
            translation TEXT,
            context     TEXT,
            example     TEXT,
            mastered    INTEGER DEFAULT 0,
            created_at  TIMESTAMP DEFAULT (datetime('now','localtime'))
        )
    """)
    # 补列：旧库逐列补齐
    existing = {r[1] for r in c.execute("PRAGMA table_info(sentences)").fetchall()}
    for col, ddl in {
        "source":           "TEXT DEFAULT '手动输入'",
        "analysis":         "TEXT",
        "structure":        "TEXT",
        "exam_points":      "TEXT",
        "seg_translation":  "TEXT",
        "full_translation": "TEXT",
        "tips":             "TEXT",
        "note":             "TEXT DEFAULT ''",
        "difficulty":       "INTEGER DEFAULT 3",
        "user_translation": "TEXT",
        "critique":         "TEXT",
    }.items():
        if col not in existing:
            c.execute(f"ALTER TABLE sentences ADD COLUMN {col} {ddl}")

    # 旧考点名迁移：倒装 -> 倒装句 等；旧版"非谓语"无法区分子类，保留原值
    rows = c.execute("SELECT id, exam_points FROM sentences WHERE exam_points IS NOT NULL").fetchall()
    for sid, pts_json in rows:
        try:
            pts = json.loads(pts_json)
        except Exception:
            continue
        new_pts = []
        for p in pts:
            mapped = config.LEGACY_POINT_MAP.get(p, p)
            new_pts.append(mapped if mapped else p)
        if new_pts != pts:
            c.execute("UPDATE sentences SET exam_points = ? WHERE id = ?",
                      (json.dumps(new_pts, ensure_ascii=False), sid))
    conn.commit()
    conn.close()


def _j(obj):
    return json.dumps(obj, ensure_ascii=False) if obj else None


def insert_sentence(stem, source, structure=None, exam_points=None,
                    seg_translation=None, full_translation=None, tips=None,
                    user_translation=None, critique=None):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO sentences (stem, source, structure, exam_points, "
        "seg_translation, full_translation, tips, user_translation, critique) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (stem, source, _j(structure), _j(exam_points), _j(seg_translation),
         full_translation, tips, user_translation, _j(critique)),
    )
    conn.commit()
    conn.close()
    return cur.lastrowid


def find_by_stem(stem):
    conn = get_conn()
    r = conn.execute("SELECT id FROM sentences WHERE stem = ? LIMIT 1", (stem,)).fetchone()
    conn.close()
    return r


def get_sentence(sid):
    conn = get_conn()
    r = conn.execute(
        """SELECT s.*, (SELECT COUNT(*) FROM reviews r WHERE r.sentence_id = s.id) AS review_count
           FROM sentences s WHERE s.id = ?""",
        (sid,),
    ).fetchone()
    conn.close()
    if not r:
        return None
    d = dict(r)
    d["points_list"] = json.loads(d["exam_points"]) if d["exam_points"] else []
    d["structure_obj"] = json.loads(d["structure"]) if d["structure"] else None
    d["seg_list"] = json.loads(d["seg_translation"]) if d["seg_translation"] else []
    d["critique_obj"] = json.loads(d["critique"]) if d["critique"] else None
    return d


def list_sentences(q="", point=""):
    conn = get_conn()
    sql = """SELECT s.id, s.stem, s.source, s.exam_points, s.created_at,
                    (SELECT COUNT(*) FROM reviews r WHERE r.sentence_id = s.id) AS review_count
             FROM sentences s WHERE 1=1"""
    args = []
    if q:
        sql += " AND s.stem LIKE ?"
        args.append(f"%{q}%")
    if point:
        sql += " AND s.exam_points LIKE ?"
        args.append(f'%"{point}"%')
    sql += " ORDER BY s.id DESC"
    rows = [dict(r) for r in conn.execute(sql, args).fetchall()]
    conn.close()
    for r in rows:
        r["points_list"] = json.loads(r["exam_points"]) if r["exam_points"] else []
    return rows


def similar_sentences(sid, points, limit=5):
    if not points:
        return []
    conn = get_conn()
    ids = []
    for p in points:
        rows = conn.execute(
            "SELECT id FROM sentences WHERE id != ? AND exam_points LIKE ? LIMIT 3",
            (sid, f'%"{p}"%'),
        ).fetchall()
        for r in rows:
            if r["id"] not in ids:
                ids.append(r["id"])
        if len(ids) >= limit:
            break
    out = []
    for i in ids[:limit]:
        r = conn.execute(
            "SELECT id, stem, exam_points, created_at FROM sentences WHERE id = ?", (i,)
        ).fetchone()
        if r:
            d = dict(r)
            d["points_list"] = json.loads(d["exam_points"]) if d["exam_points"] else []
            out.append(d)
    conn.close()
    return out


def update_note(sid, note):
    conn = get_conn()
    conn.execute(
        "UPDATE sentences SET note = ?, updated_at = datetime('now','localtime') WHERE id = ?",
        (note, sid),
    )
    conn.commit()
    conn.close()


def delete_sentence(sid):
    conn = get_conn()
    conn.execute("DELETE FROM sentences WHERE id = ?", (sid,))
    conn.commit()
    conn.close()


def insert_review(sid, user_translation, self_rating):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO reviews (sentence_id, user_translation, self_rating) VALUES (?,?,?)",
        (sid, user_translation, self_rating),
    )
    conn.commit()
    conn.close()
    return cur.lastrowid


def next_review_sentence():
    conn = get_conn()
    r = conn.execute(
        """SELECT s.id, s.stem, s.source,
                  (SELECT COUNT(*) FROM reviews r WHERE r.sentence_id = s.id) AS review_count
           FROM sentences s ORDER BY review_count ASC, RANDOM() LIMIT 1"""
    ).fetchone()
    conn.close()
    return dict(r) if r else None


def count_sentences():
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM sentences").fetchone()[0]
    conn.close()
    return n


def count_never_reviewed():
    conn = get_conn()
    n = conn.execute(
        """SELECT COUNT(*) FROM sentences s
           WHERE NOT EXISTS (SELECT 1 FROM reviews r WHERE r.sentence_id = s.id)"""
    ).fetchone()[0]
    conn.close()
    return n


def stats():
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM sentences").fetchone()[0]
    total_reviews = conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
    reviewed = conn.execute("SELECT COUNT(DISTINCT sentence_id) FROM reviews").fetchone()[0]

    point_counts = {p: 0 for p in config.EXAM_POINTS}
    for r in conn.execute("SELECT exam_points FROM sentences").fetchall():
        if not r["exam_points"]:
            continue
        for p in json.loads(r["exam_points"]):
            if p in point_counts:
                point_counts[p] += 1
    by_point = [{"point": p, "count": c} for p, c in point_counts.items() if c > 0]
    by_point.sort(key=lambda x: -x["count"])

    by_rating = [
        dict(r)
        for r in conn.execute(
            "SELECT self_rating AS rating, COUNT(*) AS count FROM reviews GROUP BY self_rating"
        ).fetchall()
    ]

    weak = {}
    for r in conn.execute(
        """SELECT r.self_rating AS rating, s.exam_points AS pts
           FROM reviews r JOIN sentences s ON s.id = r.sentence_id"""
    ).fetchall():
        if r["rating"] in ("完全不会", "意思对但表达差") and r["pts"]:
            for p in json.loads(r["pts"]):
                weak[p] = weak.get(p, 0) + 1
    weak_points = [{"point": p, "misses": c} for p, c in weak.items()]
    weak_points.sort(key=lambda x: -x["misses"])

    phrase_total = conn.execute("SELECT COUNT(*) FROM phrases").fetchone()[0]
    phrase_mastered = conn.execute("SELECT COUNT(*) FROM phrases WHERE mastered = 1").fetchone()[0]
    conn.close()
    return {
        "total_sentences": total,
        "total_reviews": total_reviews,
        "reviewed_sentences": reviewed,
        "by_point": by_point,
        "by_rating": by_rating,
        "weak_points": weak_points,
        "phrase_total": phrase_total,
        "phrase_mastered": phrase_mastered,
    }


def export_rows():
    conn = get_conn()
    rows = [
        dict(r)
        for r in conn.execute(
            "SELECT id, stem, source, exam_points, full_translation, created_at "
            "FROM sentences ORDER BY id"
        ).fetchall()
    ]
    conn.close()
    return rows


# ---------------- 必背短语 ----------------

def add_phrase(phrase, translation, context="", example="", sentence_id=None):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO phrases (sentence_id, phrase, translation, context, example) VALUES (?,?,?,?,?)",
        (sentence_id, phrase, translation, context, example),
    )
    conn.commit()
    conn.close()
    return cur.lastrowid


def list_phrases(include_mastered=True):
    conn = get_conn()
    if include_mastered:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM phrases ORDER BY mastered ASC, id DESC").fetchall()]
    else:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM phrases WHERE mastered = 0 ORDER BY id DESC").fetchall()]
    conn.close()
    return rows


def delete_phrase(pid):
    conn = get_conn()
    conn.execute("DELETE FROM phrases WHERE id = ?", (pid,))
    conn.commit()
    conn.close()


def set_phrase_mastered(pid, flag):
    conn = get_conn()
    conn.execute("UPDATE phrases SET mastered = ? WHERE id = ?", (1 if flag else 0, pid))
    conn.commit()
    conn.close()


def phrases_by_sentence(sid):
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM phrases WHERE sentence_id = ? ORDER BY id", (sid,)).fetchall()]
    conn.close()
    return rows


def quiz_phrases(n=5):
    """随机抽 n 个短语（优先未掌握的），用于匹配出题。"""
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(
        """SELECT * FROM phrases WHERE mastered = 0 ORDER BY RANDOM() LIMIT ?""", (n,)
    ).fetchall()]
    if len(rows) < n:
        extra = [dict(r) for r in conn.execute(
            """SELECT * FROM phrases WHERE mastered = 1 ORDER BY RANDOM() LIMIT ?""",
            (n - len(rows),)).fetchall()]
        rows += extra
    conn.close()
    return rows
