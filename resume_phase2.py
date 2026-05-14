"""
从 Phase 1 断点继续跑 Phase 2（ServiceImpl + Controller）
"""
import os
import sys
import time
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["LANGCHAIN_PYDANTIC_V2"] = "true"

PROJECT_NAME = "campus_v2_test"
WORKSPACE = r"C:\Users\20160\auto-graduation\workspace"
PROJECT_DIR = os.path.join(WORKSPACE, PROJECT_NAME)

# 读取已保存的设计文档
with open(os.path.join(PROJECT_DIR, "schema.sql"), "r", encoding="utf-8") as f:
    db_schema = f.read()
with open(os.path.join(PROJECT_DIR, "api.yaml"), "r", encoding="utf-8") as f:
    api_contract = f.read()

# 读取模块列表（从之前的 test_full_pipeline_v2.py 的 REPORT_TEXT 解析）
REPORT_TEXT = """
基于SpringBoot的校园闲置物品交换系统设计与实现
一、项目背景
随着互联网技术的发展，校园内的二手交易需求日益增长。
二、系统功能
1. 用户管理：学生注册、登录、个人信息管理
2. 商品管理：发布商品、编辑商品、下架商品
3. 订单管理：下单、支付（模拟）、订单状态跟踪
4. 消息通知：交易提醒、系统通知
5. 管理员后台：用户管理、商品审核、数据统计
三、技术选型
后端采用 SpringBoot 3.x + MyBatis + MySQL
"""

from agents.pm_agent import PMAgent
pm = PMAgent()
pm_result = pm.parse(REPORT_TEXT)
modules = pm_result["modules"]

# 初始化 CoderAgent
from agents.coder_agent import CoderAgent
coder = CoderAgent(
    tech_stack="java",
    project_name=PROJECT_NAME,
    db_schema=db_schema,
    api_contract=api_contract,
)

# 手动构建契约池（从磁盘读取已生成的 Phase 1 文件）
import glob
contract_pool = []
src_dir = os.path.join(PROJECT_DIR, "src/main/java/com/example/campus_v2_test")
for pattern in ["entity/*.java", "repository/*.java", "dto/*.java", "service/*.java"]:
    for fp in glob.glob(os.path.join(src_dir, pattern)):
        rel = os.path.relpath(fp, PROJECT_DIR)
        with open(fp, "r", encoding="utf-8") as f:
            content = f.read()
        contract_pool.append({"file_path": rel, "content": content})

print(f"契约池: {len(contract_pool)} 个文件")

# 只跑 Phase 2
from config import TECH_STACKS
from prompts.prompt_loader import prompts

system_prompt = prompts.load(
    "coder_system",
    tech_stack_name=TECH_STACKS["java"]["name"],
    project_name_lower=coder.project_name_safe,
)

for i, module in enumerate(modules):
    module_name, module_info = coder._normalize_module(module, i)
    
    # 检查是否已有 ServiceImpl
    impl_file = os.path.join(src_dir, f"service/impl/{module_name.replace(' ', '')}ServiceImpl.java")
    if os.path.exists(impl_file):
        print(f"[Skip] {module_name} ServiceImpl 已存在")
        continue
    
    print(f"\n[Phase 2] {i+1}/{len(modules)}: {module_name}")
    t0 = time.time()
    
    contract_hint = coder._extract_contracts(contract_pool) if contract_pool else ""
    existing_paths = [f["file_path"] for f in contract_pool]
    preset_hint = coder._get_preset_hint()
    
    try:
        files = coder._generate_phase2(
            module_name, module_info, system_prompt,
            existing_files=existing_paths,
            contract_hint=contract_hint + "\n\n" + preset_hint
        )
        t1 = time.time()
        print(f"  完成: {len(files)} 个文件, {t1-t0:.1f}s")
        
        for f in files:
            if any(x in f["file_path"] for x in ["service/impl/", "controller/"]):
                contract_pool.append(f)
    except Exception as e:
        print(f"  失败: {e}")

print("\nPhase 2 完成！")

# 编译验证
print("\n编译验证...")
import subprocess
import shutil
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

success = result.returncode == 0
error_count = result.stderr.count("[ERROR]") if result.stderr else 0

with open(os.path.join(PROJECT_DIR, "compile_phase2.log"), "w", encoding="utf-8") as f:
    f.write("STDOUT:\n" + result.stdout + "\n\nSTDERR:\n" + result.stderr)

print(f"编译: {'通过' if success else '失败'} (errors={error_count})")
if not success and error_count > 0:
    errors = [line for line in result.stderr.split('\n') if '[ERROR]' in line][:15]
    for e in errors:
        print(f"  ERR: {e[:120]}")
