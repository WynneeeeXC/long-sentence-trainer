# -*- coding: utf-8 -*-
"""SQLite 数据层：句子 + 复习记录，兼容你旧版库的平滑迁移。"""
import json
import sqlite3

import config


def get_conn():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """建表 + 旧库补列迁移（老记录只迁移 schema，数据原样保留）。"""
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
            updated_at      TIMESTAMP DEFAULT (datetime('now','localtime'))
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
    # 迁移：旧版表可能缺少这些列，逐列补齐
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
        "updated_at":       "TIMESTAMP DEFAULT (datetime('now','localtime'))",
    }.items():
        if col not in existing:
            c.execute(f"ALTER TABLE sentences ADD COLUMN {col} {ddl}")
    conn.commit()
    conn.close()


def _j(obj):
    """把结构体序列化成 JSON 字符串存库，空则 None。"""
    return json.dumps(obj, ensure_ascii=False) if obj else None


def insert_sentence(stem, source, structure=None, exam_points=None,
                    seg_translation=None, full_translation=None, tips=None):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO sentences (stem, source, structure, exam_points, "
        "seg_translation, full_translation, tips) VALUES (?,?,?,?,?,?,?)",
        (stem, source, _j(structure), _j(exam_points), _j(seg_translation),
         full_translation, tips),
    )
    conn.commit()
    conn.close()
    return cur.lastrowid


def find_by_stem(stem):
    """查重：同句原文只存一条。"""
    conn = get_conn()
    r = conn.execute("SELECT id FROM sentences WHERE stem = ? LIMIT 1", (stem,)).fetchone()
    conn.close()
    return r


def get_sentence(sid):
    """详情：附带复习次数，并把 JSON 字段解析成 Python 对象。"""
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
    return d


def list_sentences(q="", point=""):
    """列表：支持关键词搜索 + 考点筛选，按时间倒序。"""
    conn = get_conn()
    sql = """SELECT s.id, s.stem, s.source, s.exam_points, s.created_at,
                    (SELECT COUNT(*) FROM reviews r WHERE r.sentence_id = s.id) AS review_count
             FROM sentences s WHERE 1=1"""
    args = []
    if q:
        sql += " AND s.stem LIKE ?"
        args.append(f"%{q}%")
    if point:
        # exam_points 存的是 JSON 数组，按 `"考点名"` 精确匹配
        sql += " AND s.exam_points LIKE ?"
        args.append(f'%"{point}"%')
    sql += " ORDER BY s.id DESC"
    rows = [dict(r) for r in conn.execute(sql, args).fetchall()]
    conn.close()
    for r in rows:
        r["points_list"] = json.loads(r["exam_points"]) if r["exam_points"] else []
    return rows


def similar_sentences(sid, points, limit=5):
    """同类考点推荐：和本句有共同考点的其他句子。"""
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
    """删除句子（复习记录由外键级联删除）。"""
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
    """复习抽句：优先抽复习次数最少的句子（随机打散）。"""
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
    """统计：总量 / 考点分布 / 评级分布 / 薄弱考点。"""
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM sentences").fetchone()[0]
    total_reviews = conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
    reviewed = conn.execute("SELECT COUNT(DISTINCT sentence_id) FROM reviews").fetchone()[0]

    # 考点分布：统计句子库中每个考点的句子数
    point_counts = {p: 0 for p in config.EXAM_POINTS}
    for r in conn.execute("SELECT exam_points FROM sentences").fetchall():
        if not r["exam_points"]:
            continue
        for p in json.loads(r["exam_points"]):
            if p in point_counts:
                point_counts[p] += 1
    by_point = [{"point": p, "count": c} for p, c in point_counts.items() if c > 0]
    by_point.sort(key=lambda x: -x["count"])

    # 评级分布
    by_rating = [
        dict(r)
        for r in conn.execute(
            "SELECT self_rating AS rating, COUNT(*) AS count FROM reviews GROUP BY self_rating"
        ).fetchall()
    ]

    # 薄弱考点：复习时评为“完全不会/意思对但表达差”的句子，按考点累计翻车次数
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

    conn.close()
    return {
        "total_sentences": total,
        "total_reviews": total_reviews,
        "reviewed_sentences": reviewed,
        "by_point": by_point,
        "by_rating": by_rating,
        "weak_points": weak_points,
    }


def export_rows():
    """导出 CSV：给机器学习作业当标注数据用。"""
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
