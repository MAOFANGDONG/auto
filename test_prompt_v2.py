"""
轻量测试：验证 prompt 改进后 Architect 输出质量 + Coder 单模块遵循度
"""
import os
import sys
import time
import json
import shutil

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

PROJECT_NAME = "campus_prompt_v2_test"
WORKSPACE = r"C:\Users\20160\auto-graduation\workspace"
PROJECT_DIR = os.path.join(WORKSPACE, PROJECT_NAME)

# 清理旧项目
if os.path.exists(PROJECT_DIR):
    shutil.rmtree(PROJECT_DIR)
    print("[Clean] 清理旧项目")

os.makedirs(PROJECT_DIR, exist_ok=True)

# ===== Stage 1: PM Agent =====
print("\n" + "=" * 60)
print("Stage 1: PM Agent")
print("=" * 60)
t0 = time.time()

from agents.pm_agent import PMAgent
pm = PMAgent()
pm_result = pm.parse(REPORT_TEXT)
t1 = time.time()

print(f"项目: {pm_result['project_name']}")
print(f"模块: {[m['name'] for m in pm_result['modules']]}")
print(f"耗时: {t1-t0:.1f}s")

# ===== Stage 2: Architect Agent =====
print("\n" + "=" * 60)
print("Stage 2: Architect Agent")
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

# 保存设计文档
with open(os.path.join(PROJECT_DIR, "schema.sql"), "w", encoding="utf-8") as f:
    f.write(arch_result["db_schema"])
with open(os.path.join(PROJECT_DIR, "api.yaml"), "w", encoding="utf-8") as f:
    f.write(arch_result["api_contract"])

print(f"耗时: {t1-t0:.1f}s")
print(f"表数: {arch_result['db_schema'].count('CREATE TABLE')}")
print(f"API 路径数: {arch_result['api_contract'].count('/api/')}")
print(f"operationId 数: {arch_result['api_contract'].lower().count('operationid')}")
print(f"components/schemas 数: {arch_result['api_contract'].lower().count('schemas:')}")
print(f"FIELD_MAPPING 标记: {'有' if 'FIELD_MAPPING' in arch_result['api_contract'] else '无'}")

# 显示 API 契约前 2000 字符
print(f"\n--- API 契约预览 ---")
print(arch_result["api_contract"][:2000])
print("...")

# ===== Stage 3: Coder Agent 只跑第一个模块 =====
print("\n" + "=" * 60)
print("Stage 3: Coder Agent（只跑第一个模块）")
print("=" * 60)
t0 = time.time()

from agents.coder_agent import CoderAgent
from tools.project_init import init_project_from_template
from config import TECH_STACKS

init_project_from_template("java", PROJECT_NAME, PROJECT_DIR)
print(f"[Init] 项目初始化完成")

coder = CoderAgent(
    tech_stack="java",
    project_name=PROJECT_NAME,
    db_schema=arch_result["db_schema"],
    api_contract=arch_result["api_contract"],
)

# 只取第一个模块
first_module = pm_result["modules"][:1]
print(f"模块: {[m['name'] for m in first_module]}")

code_files = coder.generate_all_modules(first_module)
t1 = time.time()

java_files = [f for f in code_files if f["file_path"].endswith(".java")]
print(f"生成文件数: {len(code_files)} (Java: {len(java_files)})")
for f in java_files:
    print(f"  - {f['file_path']}")

# ===== Stage 4: 编译验证 =====
print("\n" + "=" * 60)
print("Stage 4: 编译验证")
print("=" * 60)
t0 = time.time()

import subprocess
mvnw = os.path.join(PROJECT_DIR, "mvnw.cmd")
mvn = "mvn" if shutil.which("mvn") else mvnw

original_dir = os.getcwd()
os.chdir(PROJECT_DIR)
result = subprocess.run(
    f"{mvn} clean compile -DskipTests",
    capture_output=True, text=True, timeout=300,
    encoding="utf-8", errors="ignore", shell=True,
)
os.chdir(original_dir)

t1 = time.time()
success = result.returncode == 0
error_count = result.stderr.count("[ERROR]") if result.stderr else 0

with open(os.path.join(PROJECT_DIR, "compile_test.log"), "w", encoding="utf-8") as f:
    f.write("STDOUT:\n" + result.stdout + "\n\nSTDERR:\n" + result.stderr)

print(f"耗时: {t1-t0:.1f}s")
print(f"结果: {'通过' if success else '失败'} (returncode={result.returncode})")
print(f"错误数: {error_count}")

if not success and error_count > 0:
    errors = [line for line in result.stderr.split('\n') if '[ERROR]' in line][:15]
    for e in errors:
        print(f"  ERR: {e[:120]}")

# 检查生成的代码中是否有方法嵌套问题
print("\n--- 代码结构检查 ---")
from pathlib import Path
bad_files = []
for f in java_files:
    fp = os.path.join(PROJECT_DIR, f["file_path"])
    if os.path.exists(fp):
        content = Path(fp).read_text(encoding="utf-8")
        # 简单检查：构造函数内是否嵌套方法定义
        if "public " in content:
            lines = content.split('\n')
            in_constructor = False
            brace_depth = 0
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("public ") and '(' in stripped and '{' in stripped:
                    if "class " not in stripped and "interface " not in stripped:
                        if in_constructor and brace_depth > 0:
                            bad_files.append((f["file_path"], i+1, stripped[:60]))
                if '{' in stripped:
                    brace_depth += stripped.count('{')
                if '}' in stripped:
                    brace_depth -= stripped.count('}')

if bad_files:
    print(f"发现 {len(bad_files)} 个可能有方法嵌套问题的文件:")
    for fp, line, text in bad_files[:5]:
        print(f"  {fp}:{line} {text}")
else:
    print("未发现明显的方法嵌套问题")

# 检查 Service 接口中是否有 operationId 对应的方法
print("\n--- Service 接口 vs API 契约对照 ---")
api_ops = []
import re
for match in re.finditer(r'operationId:\s*["\']?([A-Za-z]\w+)', arch_result["api_contract"], re.IGNORECASE):
    api_ops.append(match.group(1))
print(f"API 契约中的 operationId: {api_ops[:10]}{'...' if len(api_ops) > 10 else ''}")

service_files = [f for f in java_files if "service/" in f["file_path"] and "impl/" not in f["file_path"]]
for sf in service_files:
    fp = os.path.join(PROJECT_DIR, sf["file_path"])
    if os.path.exists(fp):
        content = Path(fp).read_text(encoding="utf-8")
        methods_found = []
        for op in api_ops:
            if op in content:
                methods_found.append(op)
        print(f"  {sf['file_path']}: 匹配 {len(methods_found)}/{len(api_ops)} 个 operationId")
        if methods_found:
            print(f"    匹配到: {methods_found}")

print(f"\n项目路径: {PROJECT_DIR}")
print(f"编译日志: {os.path.join(PROJECT_DIR, 'compile_test.log')}")
