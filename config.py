# -*- coding: utf-8 -*-
"""全局配置：环境变量、考点枚举、来源选项。"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 读取 .env（放在项目根目录）
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# ---- DeepSeek 配置 ----
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()

# 数据库路径（测试时可用环境变量 DB_PATH 指向临时库）
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "wynneeee.db"))

# Mock 模式：没有 API Key，或显式设置 MOCK=1 时启用（离线演示）
MOCK_MODE = os.getenv("MOCK", "0") == "1" or not DEEPSEEK_API_KEY

# ---- 固定考点枚举（细分版）----
EXAM_POINTS = [
    "定语从句", "状语从句", "名词性从句",
    "非谓语-不定式", "非谓语-动名词", "非谓语-现在分词", "非谓语-过去分词",
    "独立主格", "倒装句", "强调句", "省略句", "插入语",
    "分隔结构", "平行结构", "虚拟语气", "被动语态",
    "比较结构", "代词指代", "逻辑连接", "作者态度",
]

# 旧枚举名 -> 新枚举名（数据迁移用）
LEGACY_POINT_MAP = {
    "非谓语": None,          # 旧版无法区分子类，迁移时单独处理（先保留原值展示）
    "倒装": "倒装句",
    "强调": "强调句",
    "省略": "省略句",
}

# ---- 句子来源选项 ----
SOURCES = ["手动输入", "扇贝阅读", "考研真题翻译", "阅读真题", "日常阅读"]

# 复习时的自我评级
RATINGS = ["完全不会", "意思对但表达差", "翻译准确"]
