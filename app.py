# -*- coding: utf-8 -*-
"""Wynneeee's training · Flask 主应用（考研英语：长难句 + 短语本 + 文章精读）"""
import csv
import io
import os
import re
import random
import tempfile
import uuid

import markdown as md
from flask import Flask, Response, jsonify, render_template, request

import ai_service
import config
import database as db
import ocr_helper

app = Flask(__name__)


@app.template_filter("markdown")
def _md(s):
    return md.markdown(s or "")


# ---------------- 分析页 ----------------

@app.route("/")
def index():
    return render_template(
        "index.html",
        sources=config.SOURCES,
        exam_points=config.EXAM_POINTS,
    )


@app.post("/api/analyze")
def api_analyze():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "句子不能为空"})
    if len(text) > 2000:
        return jsonify({"ok": False, "error": "句子过长（超过 2000 字符），请拆分后再分析"})
    user_translation = (data.get("user_translation") or "").strip()
    result = ai_service.analyze_sentence(text, user_translation)
    if "error" in result:
        return jsonify({"ok": False, "error": result["error"], "raw": result.get("raw", "")})
    return jsonify({"ok": True, "result": result})


def _split_sentences(text):
    lines = [l.strip() for l in re.split(r"[\r\n]+", text) if l.strip()]
    if len(lines) > 1:
        return lines[:10]
    parts = [p.strip() for p in re.split(r"(?<=[.!?。！？])\s*", text.strip()) if p.strip()]
    return parts[:10]


@app.post("/api/batch-analyze")
def api_batch_analyze():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "内容不能为空"})
    texts = _split_sentences(text)
    if len(texts) > 10:
        return jsonify({"ok": False, "error": f"一次最多 10 句，当前切出 {len(texts)} 句，请分批"})
    results = []
    for t in texts:
        r = ai_service.analyze_sentence(t)
        dup = db.find_by_stem(t)
        if "error" in r:
            results.append({"text": t, "ok": False, "error": r["error"]})
        else:
            results.append({
                "text": t, "ok": True, "result": r,
                "duplicate": bool(dup), "dup_id": dup["id"] if dup else None,
            })
    return jsonify({"ok": True, "results": results})


@app.post("/api/save")
def api_save():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "句子不能为空"})
    dup = db.find_by_stem(text)
    if dup:
        return jsonify({"ok": True, "id": dup["id"], "duplicate": True})
    sid = db.insert_sentence(
        stem=text,
        source=data.get("source") or "手动输入",
        structure=data.get("structure"),
        exam_points=data.get("exam_points") or [],
        seg_translation=data.get("seg_translation"),
        full_translation=data.get("full_translation"),
        tips=data.get("tips"),
        user_translation=(data.get("user_translation") or "").strip() or None,
        critique=data.get("critique"),
    )
    return jsonify({"ok": True, "id": sid, "duplicate": False})


# ---------------- 句子库 ----------------

@app.route("/list")
def sentence_list():
    q = request.args.get("q", "").strip()
    point = request.args.get("exam_point", "").strip()
    rows = db.list_sentences(q=q, point=point)
    return render_template(
        "list.html", rows=rows, exam_points=config.EXAM_POINTS,
        cur_point=point, q=q,
    )


@app.route("/detail/<int:sid>")
def detail(sid):
    s = db.get_sentence(sid)
    if not s:
        return render_template("404.html"), 404
    similar = db.similar_sentences(sid, s["points_list"])
    phrases = db.phrases_by_sentence(sid)
    reviews = db.get_reviews_by_sentence(sid, limit=20)
    return render_template("detail.html", s=s, similar=similar, phrases=phrases, reviews=reviews)


@app.post("/api/sentence/<int:sid>/note")
def api_note(sid):
    if not db.get_sentence(sid):
        return jsonify({"ok": False, "error": "句子不存在"})
    data = request.get_json(silent=True) or {}
    db.update_note(sid, (data.get("note") or "").strip())
    return jsonify({"ok": True})


@app.post("/api/sentence/<int:sid>/delete")
def api_delete(sid):
    if not db.get_sentence(sid):
        return jsonify({"ok": False, "error": "句子不存在"})
    db.delete_sentence(sid)
    return jsonify({"ok": True})


# ---------------- 复习模式 ----------------

@app.route("/review")
def review_page():
    return render_template("review.html")


@app.get("/api/review/next")
def api_review_next():
    s = db.next_review_sentence()
    if not s:
        return jsonify({"ok": False, "message": "句子库还是空的，先去分析几句吧"})
    full = db.get_sentence(s["id"])
    history = db.get_reviews_by_sentence(s["id"], limit=5)
    return jsonify({"ok": True, "sentence": {
        "id": s["id"], "stem": s["stem"], "source": s["source"],
        "review_count": s["review_count"],
        "full_translation": full["full_translation"],
        "points_list": full["points_list"],
        "history": history,
        "total": db.count_sentences(),
        "remaining": db.count_never_reviewed(),
    }})


@app.post("/api/review/submit")
def api_review_submit():
    data = request.get_json(silent=True) or {}
    rating = data.get("self_rating", "")
    if rating not in config.RATINGS:
        return jsonify({"ok": False, "error": "评级无效"})
    sid = data.get("sentence_id")
    s = db.get_sentence(sid)
    if not s:
        return jsonify({"ok": False, "error": "句子不存在"})
    my = (data.get("user_translation") or "").strip()
    prev = ""
    if my:
        prev_rows = db.get_reviews_by_sentence(sid, limit=1)
        if prev_rows and prev_rows[0].get("user_translation"):
            prev = prev_rows[0]["user_translation"]
    critique = ai_service.review_critique(
        s["stem"], my, prev, s["full_translation"] or "")
    db.insert_review(sid, my, rating, critique)
    return jsonify({"ok": True, "critique": critique})


@app.post("/api/review/rate")
def api_review_rate():
    data = request.get_json(silent=True) or {}
    rating = data.get("self_rating", "")
    if rating not in config.RATINGS:
        return jsonify({"ok": False, "error": "评级无效"})
    db.update_last_review_rating(data.get("sentence_id"), rating)
    return jsonify({"ok": True})


# ---------------- 统计 ----------------

@app.route("/stats")
def stats_page():
    return render_template("stats.html")


@app.get("/api/stats")
def api_stats():
    return jsonify(db.stats())


@app.get("/api/export.csv")
def api_export():
    rows = db.export_rows()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "stem", "source", "exam_points", "full_translation", "created_at"])
    for r in rows:
        w.writerow([r["id"], r["stem"], r["source"], r["exam_points"] or "",
                    r["full_translation"] or "", r["created_at"]])
    return Response(
        "\ufeff" + buf.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=sentences_export.csv"},
    )


# ---------------- 必背短语 ----------------

@app.route("/phrases")
def phrases_page():
    rows = db.list_phrases()
    return render_template("phrases.html", rows=rows)


@app.post("/api/phrases")
def api_add_phrase():
    data = request.get_json(silent=True) or {}
    phrase = (data.get("phrase") or "").strip()
    if not phrase:
        return jsonify({"ok": False, "error": "短语不能为空"})
    pid = db.add_phrase(
        phrase=phrase,
        translation=(data.get("translation") or "").strip(),
        context=(data.get("context") or "").strip(),
        example=(data.get("example") or "").strip(),
        sentence_id=data.get("sentence_id"),
    )
    return jsonify({"ok": True, "id": pid})


@app.post("/api/phrases/<int:pid>/delete")
def api_delete_phrase(pid):
    db.delete_phrase(pid)
    return jsonify({"ok": True})


@app.post("/api/phrases/<int:pid>/mastered")
def api_phrase_mastered(pid):
    data = request.get_json(silent=True) or {}
    db.set_phrase_mastered(pid, bool(data.get("flag", False)))
    return jsonify({"ok": True})


# ---------------- 短语匹配出题 ----------------

@app.route("/quiz")
def quiz_page():
    return render_template("quiz.html")


@app.get("/api/quiz")
def api_quiz():
    n = request.args.get("n", default=5, type=int)
    rows = db.quiz_phrases(n=min(n, 10))
    if len(rows) < 2:
        return jsonify({"ok": False, "message": "短语本里至少要有 2 个短语才能出题，先去收录几个吧"})
    # 所有短语池用于生成干扰项
    pool = db.list_phrases()
    options_pool = [p for p in pool if p["translation"]]
    questions = []
    for p in rows:
        # 3 个干扰中文翻译
        distractors = [x["translation"] for x in options_pool if x["id"] != p["id"]]
        random.shuffle(distractors)
        options = distractors[:3] + [p["translation"]]
        random.shuffle(options)
        questions.append({
            "id": p["id"],
            "en": p["phrase"],
            "zh": p["translation"] or "",
            "answer": p["translation"] or "",
            "options": options,
            "context": p["context"],
        })
    return jsonify({"ok": True, "questions": questions})


# ---------------- 快捷收录（手机友好） ----------------

@app.route("/quick")
def quick_page():
    return render_template("quick.html", sources=config.SOURCES, exam_points=config.EXAM_POINTS)


# ---------------- 文章精读 ----------------

@app.route("/passage")
def passage_page():
    return render_template("passage.html", history=db.list_passages(), view=None)


@app.route("/passage/<int:pid>")
def passage_detail(pid):
    p = db.get_passage(pid)
    if not p:
        return render_template("404.html"), 404
    return render_template("passage.html", history=db.list_passages(), view=p)


@app.post("/api/passage/analyze")
def api_passage_analyze():
    """两种输入：JSON {"text": 文章} 或 multipart 表单上传图片（OCR）。"""
    text = ""
    if request.content_type and "multipart" in request.content_type:
        f = request.files.get("image")
        if not f or not f.filename:
            return jsonify({"ok": False, "error": "没有收到图片"})
        ext = os.path.splitext(f.filename)[1].lower() or ".jpg"
        if ext not in (".jpg", ".jpeg", ".png", ".bmp"):
            return jsonify({"ok": False, "error": "仅支持 jpg/png/bmp 图片"})
        tmp = os.path.join(tempfile.gettempdir(), f"passage_{uuid.uuid4().hex}{ext}")
        f.save(tmp)
        try:
            ocr = ocr_helper.ocr_image(tmp)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        if not ocr["ok"]:
            return jsonify({"ok": False, "error": ocr["error"]})
        text = ocr["text"]
    else:
        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "").strip()
        if not text:
            return jsonify({"ok": False, "error": "文章内容不能为空"})
    if len(text) < 80:
        return jsonify({"ok": False, "error": "内容太短，看起来不是一篇文章（至少 80 个字符）"})
    result = ai_service.analyze_passage(text)
    if "error" in result:
        return jsonify({"ok": False, "error": result["error"]})
    return jsonify({"ok": True, "result": result, "text": text})


@app.post("/api/passage/save")
def api_passage_save():
    data = request.get_json(silent=True) or {}
    original = (data.get("original_text") or "").strip()
    result = data.get("result")
    if not original or not result:
        return jsonify({"ok": False, "error": "缺少原文或分析结果"})
    pid = db.add_passage(
        title=(data.get("title") or "").strip(),
        source=(data.get("source") or "").strip(),
        original_text=original,
        result=result,
    )
    return jsonify({"ok": True, "id": pid})


@app.post("/api/passage/<int:pid>/delete")
def api_passage_delete(pid):
    db.delete_passage(pid)
    return jsonify({"ok": True})


if __name__ == "__main__":
    db.init_db()
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=os.getenv("FLASK_DEBUG", "1") == "1",
    )
