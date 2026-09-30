# 考研英语长难句训练营（Long Sentence Trainer）

> 为自己考研英语阅读打造的长难句学习系统：**粘贴句子 → AI 拆结构、标考点、给翻译 → 存进库 → 按考点复习 → 统计薄弱点**。

![tech](https://img.shields.io/badge/Flask-3.x-4f7a5b) ![tech](https://img.shields.io/badge/DeepSeek-API-a3c585) ![tech](https://img.shields.io/badge/SQLite-3-6f7d6a)

---

## 目录

- [为什么做这个](#为什么做这个)
- [功能总览](#功能总览)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [使用流程](#使用流程)
- [复习与统计逻辑](#复习与统计逻辑)
- [机器学习作业扩展](#机器学习作业扩展)
- [Roadmap](#roadmap)

---

## 为什么做这个

考研英语阅读里真正卡住人的不是单词，而是**长难句**。传统做法是：手机复制句子 → 贴到 Word → 开翻译软件 → 看了译文还是不懂考点 → 下次遇到还是不会。

这个项目把流程闭环起来：

```
粘贴句子 → AI 结构化分析（结构/考点/逐段翻译/整句翻译/技巧）
        → 手动确认考点 → 存入 SQLite
        → 复习模式（先自己翻译，再看答案，自评表现）
        → 统计页定位薄弱考点
```

核心原则：**先拆结构，再翻译**。结构不懂，翻译就是背答案。

---

## 功能总览

| 页面 | 功能 |
|---|---|
| 分析页 | 单句分析 + 批量导入（自动切句，最多 10 句）；考点 chips 可手动增删后保存；自动查重 |
| 句子库 | 关键词搜索 + 考点筛选；来源/时间/复习次数展示；CSV 导出 |
| 详情页 | 完整结构拆解、逐段翻译、整句翻译、翻译技巧；我的笔记；同类考点推荐；删除 |
| 复习模式 | 随机抽句（优先抽复习次数少的）→ 先写自己的翻译 → 看 AI 翻译 → 自评（完全不会 / 意思对但表达差 / 翻译准确） |
| 统计页 | 句子总数、复习覆盖率、考点分布、复习表现、薄弱考点排行 |

**固定考点枚举**（AI 输出自动归一化，统计才可靠）：

```
定语从句 / 状语从句 / 名词性从句 / 非谓语 / 倒装 / 虚拟语气
/ 强调句 / 省略 / 比较结构 / 插入语 / 独立主格
```

**离线演示模式**：没有 API Key 时自动进入关键词启发式分析，界面可完整跑通；配置 Key 后自动切换真实 AI。

---

## 技术栈

- 后端：Python + Flask 3
- AI：DeepSeek API（OpenAI SDK 兼容接口，强制 JSON 结构化输出）
- 存储：SQLite（零配置，单文件）
- 前端：原生 HTML/CSS/JS（无构建工具，抹茶绿主题）

---

## 快速开始

### 1. 克隆 & 安装

```bash
git clone https://github.com/WynneeeeXC/long-sentence-trainer.git
cd long-sentence-trainer
pip install -r requirements.txt
```

### 2. 配置 API Key

复制 `.env.example` 为 `.env`，填入你的 Key：

```bash
cp .env.example .env   # Windows: copy .env.example .env
```

```
DEEPSEEK_API_KEY=sk-你的key
```

> Key 在 [platform.deepseek.com](https://platform.deepseek.com) 申请。`.env` 已被 gitignore，不会提交到仓库。

### 3. 启动

```bash
python app.py
```

浏览器打开 http://127.0.0.1:5000

> 想先不花 token 体验界面？`set MOCK=1` 后启动即进入离线演示模式。

---

## 项目结构

```
long-sentence-trainer/
├── app.py              # Flask 路由（分析/保存/列表/详情/复习/统计/导出）
├── config.py           # 环境变量、考点枚举、来源选项
├── database.py         # SQLite 数据层（含旧库平滑迁移）
├── ai_service.py       # DeepSeek 结构化输出 + 考点归一化 + Mock 降级
├── requirements.txt
├── .env.example        # 配置模板
├── templates/          # base / index / list / detail / review / stats / 404
└── static/css/style.css
```

---

## 使用流程

1. **分析**：把读不懂的句子粘进「单句分析」，AI 返回结构拆解、考点、逐段翻译、整句翻译、翻译技巧；考点可以点击增删（AI 选的未必全对），确认后保存。
2. **批量**：从扇贝阅读 / 真题阅读复制整段，粘贴进「批量导入」，自动切句分析，一键全部保存（自动跳过重复）。
3. **复习**：每天抽几分钟进「复习模式」——先逼自己翻译，再看答案对比，最后诚实自评。
4. **统计**：看看哪个考点翻车最多，针对性补。

---

## 复习与统计逻辑

- 抽句策略：`ORDER BY 复习次数 ASC, RANDOM()` —— 优先复习没练过的句子
- 薄弱考点：复习时自评为「完全不会 / 意思对但表达差」的句子，其考点累计翻车次数排行
- 查重：同句原文只保存一条，避免库被刷脏

---

## 机器学习作业扩展

这个项目天然积累**带标注数据**，做课程作业可以直接用：

1. **文本分类**：句子库 → `导出标注数据（CSV）`，把 `exam_points` 当多标签，训练一个小分类器（sklearn 的 OneVsRest + TF-IDF 即可）来预测新句子考点。
2. **Embedding + 相似度**：用 `sentence-transformers` 对句子做向量化，找结构相似的句子（`all-MiniLM-L6-v2` 中文句也够用）。
3. **聚类**：对句子向量做 K-Means，看句子自动分成几类、每类对应什么结构。
4. **评估**：AI 翻译 vs 你自己的翻译，算 BLEU（`nltk.translate.bleu_score`）或让 AI 打分，观察"意思对但表达差"是不是普遍现象。

CSV 字段：`id, stem, source, exam_points, full_translation, created_at`

---

## Roadmap

- [x] 单句结构化分析（结构/考点/逐段翻译/整句翻译/技巧）
- [x] 固定考点枚举 + AI 归一化 + 手动修正
- [x] 批量导入、自动切句、查重
- [x] 句子库搜索/筛选、详情笔记、同类考点推荐
- [x] 复习模式（先自译 → 对比 → 自评）
- [x] 统计页（考点分布/复习表现/薄弱考点）
- [x] CSV 导出（机器学习标注数据）
- [ ] 按考点定向出题（针对薄弱点生成专项练习）
- [ ] 数据备份/多端同步
- [ ] 简单的部署版（gunicorn + 服务器）

---

MIT License
