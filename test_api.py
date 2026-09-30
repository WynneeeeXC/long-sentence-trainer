import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
API_KEY = os.getenv("DEEPSEEK_API_KEY")

# 检查有没有读到 Key
if not API_KEY:
    print("❌ 错误：没有读到 API Key，检查你的 .env 文件！")
    exit()

# 初始化 DeepSeek 客户端
client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.deepseek.com"
)

# 发送一个最简单的测试请求
try:
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "user", "content": "请回复一句：连接成功！"}
        ]
    )
    print("✅ 大模型回复：", response.choices[0].message.content)
except Exception as e:
    print("❌ 请求失败，报错：", e)