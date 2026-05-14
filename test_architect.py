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
print(f"项目: {pm_result['project_name']}")
print(f"模块数: {len(pm_result['modules'])}")
print("正在调用 LLM 设计数据库 Schema + API 契约...")
print()

architect = ArchitectAgent()
result = architect.design(
    project_name=pm_result['project_name'],
    tech_stack='java',
    modules=pm_result['modules'],
    requirements_summary=json.dumps(pm_result, ensure_ascii=False),
)

# 保存到项目目录
project_dir = os.path.join(WORKSPACE_DIR, pm_result['project_name'])
os.makedirs(project_dir, exist_ok=True)

with open(os.path.join(project_dir, 'schema.sql'), 'w', encoding='utf-8') as f:
    f.write(result['db_schema'])
with open(os.path.join(project_dir, 'api.yaml'), 'w', encoding='utf-8') as f:
    f.write(result['api_contract'])

print('--- 数据库 Schema ---')
print(f"表数量: {result['db_schema'].count('CREATE TABLE')}")
print(f"Schema 长度: {len(result['db_schema'])} 字符")
print()

print('--- API 契约 ---')
print(f"API 长度: {len(result['api_contract'])} 字符")
print()

print('--- 项目结构 ---')
print(result.get('project_structure', 'N/A'))
print()

print(f"文件已保存到: {project_dir}")
print("  - schema.sql")
print("  - api.yaml")
