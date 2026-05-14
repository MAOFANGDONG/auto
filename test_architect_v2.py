import json
import os
from agents.architect_agent import ArchitectAgent
from config import WORKSPACE_DIR

# 加载 PM Agent 结果
with open(r'C:\Users\20160\auto-graduation\workspace\blindbox_pm_result.json', 'r', encoding='utf-8') as f:
    pm_result = json.load(f)

print('=' * 60)
print('[STEP 2] Architect Agent 设计架构')
print('=' * 60)

project_dir = os.path.join(WORKSPACE_DIR, pm_result['project_name'])
os.makedirs(project_dir, exist_ok=True)

architect = ArchitectAgent()

# ===== 阶段 1: Schema =====
print("[阶段 1/2] 生成数据库 Schema...")
schema_prompt = architect._call_api.__self__  # 无法直接调用私有方法，改用完整流程

# 直接调用 design 方法
result = architect.design(
    project_name=pm_result['project_name'],
    tech_stack='java',
    modules=pm_result['modules'],
    requirements_summary=json.dumps(pm_result, ensure_ascii=False),
)

# 保存
with open(os.path.join(project_dir, 'schema.sql'), 'w', encoding='utf-8') as f:
    f.write(result['db_schema'])
with open(os.path.join(project_dir, 'api.yaml'), 'w', encoding='utf-8') as f:
    f.write(result['api_contract'])

print()
print('--- 完成 ---')
print(f"Schema 表数: {result['db_schema'].count('CREATE TABLE')}")
print(f"API 契约长度: {len(result['api_contract'])} 字符")
print(f"文件保存位置: {project_dir}")
