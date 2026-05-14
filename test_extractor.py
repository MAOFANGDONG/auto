"""
测试 contract_extractor
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.contract_extractor import extract_module_contracts

# 读取之前成功生成的 api.yaml 和 schema.sql
with open(r"C:\Users\20160\auto-graduation\workspace\architect_direct_test\api.yaml", "r", encoding="utf-8") as f:
    api_yaml = f.read()
with open(r"C:\Users\20160\auto-graduation\workspace\architect_direct_test\schema.sql", "r", encoding="utf-8") as f:
    db_schema = f.read()

modules = [
    {"name": "用户管理", "entities": ["用户"]},
    {"name": "商品管理", "entities": ["商品"]},
    {"name": "订单管理", "entities": ["订单"]},
]

contracts = extract_module_contracts(api_yaml, db_schema, modules)

for name, text in contracts.items():
    print(f"\n{'='*60}")
    print(f"模块: {name}")
    print(f"{'='*60}")
    print(text)
