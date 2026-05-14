"""
直接调用 OpenAI API 测试 Architect prompt，绕开 LangChain 和 Agent 封装
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI
import httpx

API_KEY = os.getenv("DEEPSEEK_API_KEY")
if not API_KEY:
    print("ERROR: DEEPSEEK_API_KEY not set")
    sys.exit(1)

client = OpenAI(
    base_url="https://api.deepseek.com/v1",
    api_key=API_KEY,
    timeout=120,
    max_retries=2,
    http_client=httpx.Client(timeout=httpx.Timeout(120.0, connect=10, read=120, write=30)),
)

PROMPT = """你是一位资深系统架构师，擅长设计数据库和 API 接口。

## 任务
基于以下需求，设计数据库 Schema 和 RESTful API 契约。

## 输入信息
- 项目名称：校园闲置物品交换系统
- 技术栈：java
- 功能模块：[{'name': '用户与权限管理', 'description': '学生注册、登录、个人信息管理'}, {'name': '商品管理', 'description': '发布商品、编辑商品、下架商品'}, {'name': '订单管理', 'description': '下单、支付（模拟）、订单状态跟踪'}]
- 核心实体：User, Product, Order
- 用户角色：学生, 管理员
- 约束条件：用户密码必须加密存储

## 输出要求

### 1. 数据库 Schema（SQL）
使用标准 SQL 语法，包含 CREATE TABLE 语句、主键、外键、索引、注释。

### 2. OpenAPI 契约（YAML）
使用 OpenAPI 3.0 格式，每个接口必须包含：
- operationId（有效的 Java 方法名）
- 完整的 parameters（name, in, schema.type, required, description）
- requestBody 引用 components/schemas
- responses 引用 components/schemas
- components/schemas 必须包含每个 DTO 的完整字段列表

在 YAML 末尾用注释输出字段映射表：
# === FIELD_MAPPING ===
# Entity: User → DTO: UserDTO 的字段对应关系

### 3. 项目目录结构
文本树形式。

## 输出格式
严格按照以下结构输出，用 === 分隔：

=== DATABASE_SCHEMA ===
[SQL 代码]

=== OPENAPI_CONTRACT ===
[YAML 代码]

=== PROJECT_STRUCTURE ===
[目录树]

## 规则
- 不要输出任何解释，只输出三部分代码
- 不要使用 Markdown 代码块标记（```）
- Schema 必须完整，不要省略任何表或字段
"""

print("调用 LLM...")
t0 = time.time()
response = client.chat.completions.create(
    model="deepseek-v4-pro",
    messages=[{"role": "user", "content": PROMPT}],
    temperature=0.1,
    max_tokens=8192,
)
t1 = time.time()
content = response.choices[0].message.content

print(f"耗时: {t1-t0:.1f}s, 长度: {len(content)} 字符")
print(f"\n{'='*60}")
print("原始输出：")
print(content)
print(f"{'='*60}")

# 解析
import re
sections = {"db_schema": "", "api_contract": "", "project_structure": ""}
patterns = {
    "db_schema": r"===\s*DATABASE_SCHEMA\s*===(.*?)===\s*OPENAPI_CONTRACT\s*===",
    "api_contract": r"===\s*OPENAPI_CONTRACT\s*===(.*?)===\s*PROJECT_STRUCTURE\s*===",
    "project_structure": r"===\s*PROJECT_STRUCTURE\s*===(.*)$",
}
for key, pattern in patterns.items():
    match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
    if match:
        sections[key] = match.group(1).strip()

print(f"\n解析结果:")
print(f"  db_schema: {len(sections['db_schema'])} 字符, CREATE TABLE: {sections['db_schema'].count('CREATE TABLE')}")
print(f"  api_contract: {len(sections['api_contract'])} 字符, /api/: {sections['api_contract'].count('/api/')}")
print(f"  operationId: {len([l for l in sections['api_contract'].split(chr(10)) if 'operationId' in l])}")
print(f"  FIELD_MAPPING: {'有' if 'FIELD_MAPPING' in sections['api_contract'] else '无'}")
print(f"  project_structure: {len(sections['project_structure'])} 字符")

# 保存
out_dir = r"C:\Users\20160\auto-graduation\workspace\architect_direct_test"
os.makedirs(out_dir, exist_ok=True)
with open(os.path.join(out_dir, "raw_output.txt"), "w", encoding="utf-8") as f:
    f.write(content)
with open(os.path.join(out_dir, "api.yaml"), "w", encoding="utf-8") as f:
    f.write(sections["api_contract"])
with open(os.path.join(out_dir, "schema.sql"), "w", encoding="utf-8") as f:
    f.write(sections["db_schema"])

print(f"\n已保存到: {out_dir}")
