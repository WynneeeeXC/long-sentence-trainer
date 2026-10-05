# -*- coding: utf-8 -*-
"""AI 分析服务：
- 有 API Key 时调用 DeepSeek，强制 JSON 结构化输出；
- 考点自动归一化到固定枚举（config.EXAM_POINTS）；
- 自动挑出值得背的固定表达（phrases）；
- 用户给译文时给出一针见血的点评（critique）；
- 无 Key / MOCK=1 时走关键词启发式，保证界面可离线演示。
"""
import json
import re
import time

from openai import OpenAI

import config

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL,
            timeout=60.0,
            max_retries=2,
        )
    return _client


def _chat(messages):
    """带重试的 chat 调用：网络瞬时错误自动重试 2 次。"""
    client = _get_client()
    last_err = None
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=config.DEEPSEEK_MODEL,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            last_err = e
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    raise last_err


# 考点别名 → 枚举标准名（AI 说法可能飘，这里统一收口；顺序敏感：先具体后泛化）
_ALIASES = [
    ("不定式", "非谓语-不定式"),
    ("动名词", "非谓语-动名词"),
    ("现在分词", "非谓语-现在分词"),
    ("过去分词", "非谓语-过去分词"),
    ("分词", "非谓语-现在分词"),
    ("定语", "定语从句"),
    ("状语", "状语从句"),
    ("名词性", "名词性从句"),
    ("独立主格", "独立主格"),
    ("倒装", "倒装句"),
    ("虚拟", "虚拟语气"),
    ("强调", "强调句"),
    ("省略", "省略句"),
    ("比较", "比较结构"),
    ("插入", "插入语"),
    ("分隔", "分隔结构"),
    ("平行", "平行结构"),
    ("被动", "被动语态"),
    ("指代", "代词指代"),
    ("逻辑连接", "逻辑连接"),
    ("作者态度", "作者态度"),
    ("态度", "作者态度"),
]


def normalize_points(points):
    """把 AI 返回的考点文本归一化到固定枚举：去重、保枚举序。"""
    if not points:
        return []
    text = " ".join(str(p) for p in points)
    found = []
    for alias, canon in _ALIASES:
        if alias in text and canon not in found:
            found.append(canon)
    return found


SYSTEM_PROMPT = (
    "你是考研英语长难句分析专家。任务：拆解句子结构、标注语法/阅读考点、按意群翻译、给出整句翻译和翻译技巧。\n"
    "考点只能从以下枚举中选择（可多选，也可以不选）：\n"
    + "、".join(config.EXAM_POINTS) +
    "\n另外挑出 0-3 个句子里值得背诵的地道固定表达（短语/搭配/习语），放进 phrases。"
    "如果用户提供了自己的译文，请给出 critique：一针见血指出他的译文哪里不对/哪里生硬，并给出更地道的改法。\n"
    "严格只输出一个 JSON 对象，不要输出任何解释、Markdown 代码块或其他内容。JSON 格式：\n"
    '{"structure": {"main": "主句结构说明", '
    '"clauses": [{"type": "从句/非谓语类型", "text": "片段", "modifies": "修饰对象或作用"}], '
    '"non_finite": "非谓语说明，没有则为空字符串"}, '
    '"exam_points": ["考点1", "考点2"], '
    '"seg_translation": [{"en": "英文意群", "zh": "中文翻译"}], '
    '"full_translation": "整句通顺的中文翻译", '
    '"tips": "考研翻译技巧1-3句", '
    '"phrases": [{"en": "固定表达", "zh": "中文", "tip": "用法/为什么值得背"}], '
    '"critique": {"verdict": "一句话总评", "problems": ["具体问题（指出原文位置）"], "better": "更地道的译文"}'
    "}"
)


def analyze_with_ai(text: str, user_translation: str = "") -> dict:
    """调用 DeepSeek，返回结构化结果字典；异常时返回 {"error": ...}。"""
    user_content = f"请分析这个句子：\n{text}"
    if user_translation:
        user_content += f"\n\n我的译文：{user_translation}\n请在分析之外，额外给出 critique 字段点评我的译文。"
    try:
        content = _chat([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ])
        return _parse_result(content)
    except Exception as e:
        return {"error": f"AI 调用失败（已重试）：{e}"}


def _parse_result(content: str) -> dict:
    """解析 AI 返回：先试整体 JSON，再试提取花括号块，最后兜底。"""
    data = None
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", content)
        if m:
            try:
                data = json.loads(m.group(0))
            except json.JSONDecodeError:
                data = None
    if not isinstance(data, dict):
        return {"error": "AI 返回格式无法解析，请重试一次", "raw": content[:500]}

    data["exam_points"] = normalize_points(data.get("exam_points") or [])
    st = data.get("structure")
    if not isinstance(st, dict):
        st = {"main": "", "clauses": [], "non_finite": ""}
    st["clauses"] = st.get("clauses") or []
    data["structure"] = st
    data["seg_translation"] = data.get("seg_translation") or []
    data["full_translation"] = data.get("full_translation") or ""
    data["tips"] = data.get("tips") or ""
    data["phrases"] = data.get("phrases") or []
    if not isinstance(data.get("critique"), dict):
        data["critique"] = None
    return data


# ---------- Mock 模式（离线演示，关键词启发式） ----------

_MOCK_RULES = [
    (r"\b(which|that|who|whom|whose|where|when)\b", "定语从句"),
    (r"\b(because|although|though|if|unless|while|since|so that|even if|as long as|whereas)\b", "状语从句"),
    (r"\b(what|whether|whoever|whatever|whomever)\b", "名词性从句"),
    (r"\b(never|rarely|hardly|scarcely|not only|no sooner)\b", "倒装句"),
    (r"\b(if only|wish|would rather|had better|suggest|insist|demand|require)\b", "虚拟语气"),
    (r"\bit (is|was) .+\bthat\b", "强调句"),
    (r"\b(more|most|less|least|than|as)\b", "比较结构"),
    (r",\s*(however|for example|of course|i think|indeed|in my view|say)\s*,", "插入语"),
    (r"\b(by|with|through|via) .+ (done|completed|made|used)\b", "被动语态"),
]


def analyze_mock(text: str, user_translation: str = "") -> dict:
    """离线演示：命中关键词即标考点，翻译位置给提示。"""
    t = text.strip()
    low = t.lower()
    points = []
    for pattern, name in _MOCK_RULES:
        if re.search(pattern, low) and name not in points:
            points.append(name)
    segments = [x.strip() for x in re.split(r"(?<=[,;:，；：])\s*", t) if x.strip()]
    result = {
        "structure": {
            "main": t,
            "clauses": [
                {"type": p, "text": f"（离线演示模式：命中「{p}」关键词）",
                 "modifies": "配置 DEEPSEEK_API_KEY 后由 AI 精拆"}
                for p in points[:3]
            ],
            "non_finite": "",
        },
        "exam_points": points,
        "seg_translation": [{"en": s, "zh": "（离线模式无翻译）"} for s in segments[:12]],
        "full_translation": "（离线演示模式：未调用 AI。在 .env 填入 DEEPSEEK_API_KEY 并重启后，即可获得完整结构拆解与翻译。）",
        "tips": "（离线演示模式仅做关键词启发式，仅供界面测试，不要当作真实分析。）",
        "phrases": [],
        "critique": None,
    }
    if user_translation:
        result["critique"] = {
            "verdict": "（离线模式）",
            "problems": ["配置 API Key 后 AI 会一针见血点评你的译文"],
            "better": "",
        }
    return result


def analyze_sentence(text: str, user_translation: str = "") -> dict:
    """统一入口：Mock 模式走启发式，否则调用 DeepSeek。"""
    if config.MOCK_MODE:
        return analyze_mock(text, user_translation)
    return analyze_with_ai(text, user_translation)


# ---------------- 复习点评（含历史对比 + 高级表达） ----------------

def review_critique(text: str, current_translation: str, previous_translation: str = "",
                    full_translation: str = "") -> dict:
    """复习场景的译文点评：可对比上一次译文，附带高级表达建议。"""
    if config.MOCK_MODE:
        return {
            "verdict": "（离线演示模式）",
            "problems": ["配置 DEEPSEEK_API_KEY 后，AI 会对比你的译文和历史译文逐条点评"],
            "better": full_translation or "",
            "improvement": "（离线模式无历史对比）",
            "advanced": [],
        }
    user = (
        f"英文原句：{text}\n"
        f"本次译文：{current_translation}\n"
    )
    if previous_translation:
        user += f"上次译文：{previous_translation}\n"
    if full_translation:
        user += f"参考翻译：{full_translation}\n"
    try:
        content = _chat([
            {"role": "system", "content": REVIEW_CRITIQUE_PROMPT},
            {"role": "user", "content": user},
        ])
        data = _parse_result(content)
        if "error" in data:
            return data
        data["verdict"] = data.get("verdict") or ""
        data["problems"] = data.get("problems") or []
        data["better"] = data.get("better") or ""
        data["improvement"] = data.get("improvement") or ""
        data["advanced"] = data.get("advanced") or []
        return data
    except Exception as e:
        return {"error": f"AI 调用失败（已重试）：{e}"}


REVIEW_CRITIQUE_PROMPT = (
    "你是考研英语翻译批改老师。用户复习一个句子时写了译文，你要一针见血点评。\n"
    "严格输出一个 JSON 对象，格式：\n"
    '{"verdict": "一句话总评", '
    '"problems": ["具体问题，指出对应英文位置和原因"], '
    '"better": "更地道、更贴原文的完整译文", '
    '"improvement": "对比上次译文，这次进步或退步在哪里（没有上次译文就写首次练习）", '
    '"advanced": [{"en": "高级表达", "zh": "意思", "usage": "在句子里怎么用/替换了哪个普通说法"}]}\n'
    "要求：problems 不超过 3 条、advanced 给出 1-3 个能把译文说得更高级的表达（替换口语化/直译说法）。"
)


# ---------------- 出题练习点评 ----------------

QUIZ_CRITIQUE_PROMPT = (
    "你是考研英语翻译批改老师。用户在翻译练习中写了一个答案，你要一针见血点评。\n"
    "严格输出一个 JSON 对象，格式：\n"
    '{"score": 0到100的整数, '
    '"verdict": "一句话总评", '
    '"problems": ["具体问题，指出对应位置和原因"], '
    '"better": "更地道的完整参考答案"}\n'
    "要求：problems 不超过 3 条；如果是中译英，注意检查语法、搭配、是否直译腔；"
    "如果是英译中，注意检查是否漏译、错译、翻译腔。score 按考研翻译评分标准（准确、通顺、完整）打分。"
)


def quiz_critique(question: str, reference: str, user_answer: str, direction: str) -> dict:
    """出题练习点评：direction 为 zh2en（中译英）或 en2zh（英译中）。"""
    if config.MOCK_MODE:
        return {
            "score": 0,
            "verdict": "（离线演示模式）",
            "problems": ["配置 DEEPSEEK_API_KEY 后，AI 会一针见血点评你的作答"],
            "better": reference,
        }
    user = (
        f"练习类型：{'中译英' if direction == 'zh2en' else '英译中'}\n"
        f"题目：{question}\n"
        f"参考答案：{reference}\n"
        f"我的作答：{user_answer}\n"
    )
    try:
        content = _chat([
            {"role": "system", "content": QUIZ_CRITIQUE_PROMPT},
            {"role": "user", "content": user},
        ])
        data = _parse_result(content)
        if "error" in data:
            return data
        data["score"] = int(data.get("score") or 0)
        data["verdict"] = data.get("verdict") or ""
        data["problems"] = data.get("problems") or []
        data["better"] = data.get("better") or ""
        return data
    except Exception as e:
        return {"error": f"AI 调用失败（已重试）：{e}"}


# ---------------- 文章精读 ----------------

PASSAGE_SYSTEM_PROMPT = (
    "你是考研英语阅读精读专家。把用户给的一篇考研难度英文文章，做成一份「不要废话」的精读笔记，严格输出一个 JSON 对象：\n"
    '{"vocab": [{"word": "熟词僻义词/表达", "meaning": "在文中的含义", "tip": "为什么是僻义/记忆点"}], '
    '"phrases": [{"en": "外刊高频词组", "zh": "中文", "tip": "用法"}], '
    '"paragraphs": [{"n": "段落序号", "summary": "一句话概括该段主旨"}], '
    '"translation": "整篇通顺的中文翻译（按段落连贯翻译）", '
    '"main_idea": "全文中心思想（一两句话）", '
    '"attitude": "作者整体态度：支持/反对/怀疑/客观中立（任选其一，可加一两个词修饰）", '
    '"questions": [{"q": "考研阅读理解题题干", "options": ["A. ...", "B. ...", "C. ...", "D. ..."], '
    '"answer": "正确选项字母", "explain": "解析（为什么对/为什么错）"}]}\n'
    "要求：vocab 3-6 条、phrases 3-6 条、paragraphs 逐段、questions 恰好 5 题，题型贴近考研阅读（主旨/细节/推断/态度/词义），选项必须 4 个且带 A./B./C./D. 前缀。"
)


def analyze_passage(text: str) -> dict:
    """整篇文章精读：熟词僻义/高频词组/段落主旨/全文翻译/中心思想/态度/5 道选择题。"""
    if config.MOCK_MODE:
        return {"error": "（离线演示模式不支持文章精读）在 .env 配置 DEEPSEEK_API_KEY 后可用"}
    try:
        content = _chat([
            {"role": "system", "content": PASSAGE_SYSTEM_PROMPT},
            {"role": "user", "content": f"请精读这篇文章并按要求输出：\n\n{text[:6000]}"},
        ])
        data = _parse_result(content)
        if "error" in data:
            return data
        data["vocab"] = data.get("vocab") or []
        data["phrases"] = data.get("phrases") or []
        data["paragraphs"] = data.get("paragraphs") or []
        data["translation"] = data.get("translation") or ""
        data["main_idea"] = data.get("main_idea") or ""
        data["attitude"] = data.get("attitude") or "客观中立"
        data["questions"] = data.get("questions") or []
        return data
    except Exception as e:
        return {"error": f"AI 调用失败（已重试）：{e}"}
