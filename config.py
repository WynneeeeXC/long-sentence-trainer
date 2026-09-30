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

# ---- 固定考点枚举（统计、筛选、AI 输出归一化都依赖它，不要随意改）----
EXAM_POINTS = [
    "定语从句",
    "状语从句",
    "名词性从句",
    "非谓语",
    "倒装",
    "虚拟语气",
    "强调句",
    "省略",
    "比较结构",
    "插入语",
    "独立主格",
]

# ---- 句子来源选项 ----
SOURCES = ["手动输入", "扇贝阅读", "考研真题翻译", "阅读真题", "日常阅读"]

# 复习时的自我评级
RATINGS = ["完全不会", "意思对但表达差", "翻译准确"]
