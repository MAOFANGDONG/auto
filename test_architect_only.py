"""
轻量测试：只跑 Architect，验证 prompt 改进后的 API 契约质量
"""
import os
import sys
import time
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["LANGCHAIN_PYDANTIC_V2"] = "true"

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

# ===== PM Agent =====
print("=" * 60)
print("PM Agent")
print("=" * 60)
t0 = time.time()
from agents.pm_agent import PMAgent
pm = PMAgent()
pm_result = pm.parse(REPORT_TEXT)
t1 = time.time()
print(f"耗时: {t1-t0:.1f}s, 模块: {[m['name'] for m in pm_result['modules']]}")

# ===== Architect Agent =====
print("\n" + "=" * 60)
print("Architect Agent")
print("=" * 60)
t0 = time.time()
from agents.architect_agent import ArchitectAgent
architect = ArchitectAgent()
arch_result = architect.design(
    project_name=pm_result["project_name"],
    tech_stack="java",
    modules=pm_result["modules"],
    requirements_summary=json.dumps(pm_result, ensure_ascii=False),
)
t1 = time.time()

print(f"耗时: {t1-t0:.1f}s")
print(f"表数: {arch_result['db_schema'].count('CREATE TABLE')}")
print(f"API 路径数: {arch_result['api_contract'].count('/api/')}")
print(f"operationId 数: {len([l for l in arch_result['api_contract'].split(chr(10)) if 'operationId' in l])}")
print(f"FIELD_MAPPING: {'有' if 'FIELD_MAPPING' in arch_result['api_contract'] else '无'}")

# 保存到文件便于查看
out_dir = r"C:\Users\20160\auto-graduation\workspace\architect_test"
os.makedirs(out_dir, exist_ok=True)
with open(os.path.join(out_dir, "schema.sql"), "w", encoding="utf-8") as f:
    f.write(arch_result["db_schema"])
with open(os.path.join(out_dir, "api.yaml"), "w", encoding="utf-8") as f:
    f.write(arch_result["api_contract"])
with open(os.path.join(out_dir, "structure.txt"), "w", encoding="utf-8") as f:
    f.write(arch_result["project_structure"])

# 显示 API 契约
print(f"\n--- API 契约 (前 3000 字符) ---")
print(arch_result["api_contract"][:3000])
print("...")

print(f"\n文件已保存到: {out_dir}")
