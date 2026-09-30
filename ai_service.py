# -*- coding: utf-8 -*-
"""AI 分析服务：
- 有 API Key 时调用 DeepSeek，强制 JSON 结构化输出；
- 考点自动归一化到固定枚举（config.EXAM_POINTS）；
- 无 Key / MOCK=1 时走关键词启发式，保证界面可离线演示。
"""
import json
import re

from openai import OpenAI

import config

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=config.DEEPSEEK_API_KEY, base_url=config.DEEPSEEK_BASE_URL)
    return _client


# 考点别名 → 枚举标准名（AI 说法可能飘，这里统一收口）
_ALIASES = {
    "定语": "定语从句",
    "状语": "状语从句",
    "名词性": "名词性从句",
    "名词": "名词性从句",
    "非谓语动词": "非谓语",
    "非谓语": "非谓语",
    "倒装": "倒装",
    "虚拟": "虚拟语气",
    "强调": "强调句",
    "省略": "省略",
    "比较": "比较结构",
    "插入": "插入语",
    "独立主格": "独立主格",
}


def normalize_points(points):
    """把 AI 返回的考点文本归一化到固定枚举：去重、按枚举顺序。"""
    if not points:
        return []
    text = " ".join(str(p) for p in points)
    found = []
    for alias, canon in _ALIASES.items():
        if alias in text and canon not in found:
            found.append(canon)
    return found


SYSTEM_PROMPT = (
    "你是考研英语长难句分析专家。任务：拆解句子结构、标注语法考点、按意群翻译、给出整句翻译和翻译技巧。\n"
    "考点只能从以下枚举中选择（可多选，也可以不选）：\n"
    + "、".join(config.EXAM_POINTS) +
    "\n严格只输出一个 JSON 对象，不要输出任何解释、Markdown 代码块或其他内容。JSON 格式：\n"
    '{"structure": {"main": "主句结构说明", '
    '"clauses": [{"type": "从句/非谓语类型", "text": "从句或非谓语片段", "modifies": "修饰对象或作用"}], '
    '"non_finite": "非谓语说明，没有则为空字符串"}, '
    '"exam_points": ["考点1", "考点2"], '
    '"seg_translation": [{"en": "英文意群", "zh": "中文翻译"}], '
    '"full_translation": "整句通顺的中文翻译", '
    '"tips": "考研翻译时需要注意的技巧，结合考点写1-3句"}'
)


def analyze_with_ai(text: str) -> dict:
    """调用 DeepSeek，返回结构化结果字典；异常时返回 {"error": ...}。"""
    try:
        resp = _get_client().chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"请分析这个句子：\n{text}"},
            ],
            response_format={"type": "json_object"},  # DeepSeek 的 JSON 输出模式
            temperature=0.3,
        )
        content = resp.choices[0].message.content or ""
        return _parse_result(content)
    except Exception as e:  # 网络、限流、Key 失效等都走这里
        return {"error": f"AI 调用失败：{e}"}


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
    return data


# ---------- Mock 模式（离线演示，关键词启发式） ----------

_MOCK_RULES = [
    (r"\b(which|that|who|whom|whose|where|when)\b", "定语从句"),
    (r"\b(because|although|though|if|unless|while|since|so that|even if|as long as|whereas)\b", "状语从句"),
    (r"\b(what|whether|whoever|whatever|whomever)\b", "名词性从句"),
    (r",\s*\w+ing\b|\b\w+ing\b,\s*", "非谓语"),
    (r"\b(never|rarely|hardly|scarcely|not only|no sooner)\b", "倒装"),
    (r"\b(if only|wish|would rather|had better|suggest|insist|demand|require)\b", "虚拟语气"),
    (r"\bit (is|was) .+\bthat\b", "强调句"),
    (r"\b(more|most|less|least|than|as)\b", "比较结构"),
    (r",\s*(however|for example|of course|i think|indeed|in my view|say)\s*,", "插入语"),
]


def analyze_mock(text: str) -> dict:
    """离线演示：命中关键词即标考点，翻译位置给提示。"""
    t = text.strip()
    low = t.lower()
    points = []
    for pattern, name in _MOCK_RULES:
        if re.search(pattern, low) and name not in points:
            points.append(name)
    segments = [x.strip() for x in re.split(r"(?<=[,;:，；：])\s*", t) if x.strip()]
    return {
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
    }


def analyze_sentence(text: str) -> dict:
    """统一入口：Mock 模式走启发式，否则调用 DeepSeek。"""
    if config.MOCK_MODE:
        return analyze_mock(text)
    return analyze_with_ai(text)
