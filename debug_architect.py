"""
调试 Architect Agent：保存 LLM 原始输出，检查解析问题
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from agents.architect_agent import ArchitectAgent
from agents.pm_agent import PMAgent

REPORT_TEXT = """
基于SpringBoot的校园闲置物品交换系统设计与实现
一、项目背景
随着互联网技术的发展，校园内的二手交易需求日益增长。
二、系统功能
1. 用户管理：学生注册、登录、个人信息管理
2. 商品管理：发布商品、编辑商品、下架商品
3. 订单管理：下单、支付（模拟）、订单状态跟踪
三、技术选型
后端采用 SpringBoot 3.x + MyBatis + MySQL
"""

print("[PM] 解析需求...")
pm = PMAgent()
pm_result = pm.parse(REPORT_TEXT)
print(f"模块: {[m['name'] for m in pm_result['modules']]}")

print("\n[Architect] 调用 LLM...")
architect = ArchitectAgent()

# 手动调用 design 的 prompt 构建逻辑
from prompts.prompt_loader import prompts

entities_str, actors_str, constraints_str, relationships_str = architect._extract_from_requirements(
    json.dumps(pm_result, ensure_ascii=False)
)

prompt = prompts.load(
    "architect_agent",
    project_name=pm_result["project_name"],
    tech_stack="java",
    modules=str(pm_result["modules"]),
    entities=entities_str,
    actors=actors_str,
    constraints=constraints_str,
    relationships=relationships_str,
)

print(f"\nPrompt 长度: {len(prompt)} 字符")

# 调用 LLM
content = architect._call_api(prompt)
print(f"LLM 输出长度: {len(content)} 字符")

# 保存原始输出
out_dir = r"C:\Users\20160\auto-graduation\workspace\architect_debug"
os.makedirs(out_dir, exist_ok=True)
with open(os.path.join(out_dir, "raw_output.txt"), "w", encoding="utf-8") as f:
    f.write(content)

print(f"\n原始输出已保存到: {out_dir}\raw_output.txt")

# 解析
result = architect._parse_sections(content)
print(f"\n解析结果:")
for k, v in result.items():
    print(f"  {k}: {len(v)} 字符")

# 显示前 2000 字符
print(f"\n--- 原始输出前 2000 字符 ---")
print(content[:2000])
print("...")
print(f"\n--- 原始输出后 2000 字符 ---")
print(content[-2000:])
