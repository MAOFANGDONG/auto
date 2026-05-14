"""
完整流程端到端测试
依次验证：PM -> Architect -> Coder Phase1 -> 编译 -> Coder Phase2 -> 编译
"""
import os
import sys
import time
import json
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["LANGCHAIN_PYDANTIC_V2"] = "true"

from loguru import logger

# 日志输出到文件便于查看
logger.add("test_pipeline.log", rotation="10 MB", level="INFO")

REPORT_TEXT = """
基于SpringBoot的校园闲置物品交换系统设计与实现

一、项目背景
随着互联网技术的发展，校园内的二手交易需求日益增长。本系统旨在为高校学生提供一个安全、便捷的二手物品交易平台。

二、系统功能
1. 用户管理：学生注册、登录、个人信息管理
2. 商品管理：发布商品、编辑商品、下架商品、商品分类
3. 订单管理：下单、支付（模拟）、订单状态跟踪
4. 消息通知：交易提醒、系统通知
5. 管理员后台：用户管理、商品审核、数据统计

三、技术选型
后端采用 SpringBoot 3.x + MyBatis + MySQL
前端采用 Vue3 + Element Plus
移动端采用微信小程序

四、性能要求
系统并发用户数不低于 100 人，页面响应时间不超过 2 秒。
"""

PROJECT_NAME = "campus_secondhand_test"
WORKSPACE = r"C:\Users\20160\auto-graduation\workspace"
PROJECT_DIR = os.path.join(WORKSPACE, PROJECT_NAME)

results = {"stages": {}}

def record_stage(name, start_time, end_time, success, details):
    results["stages"][name] = {
        "start": start_time,
        "end": end_time,
        "duration_sec": round(end_time - start_time, 1),
        "success": success,
        "details": details,
    }
    status = "OK" if success else "FAIL"
    print(f"\n[{status}] {name}: {round(end_time - start_time, 1)}s")
    if details:
        print(f"       {details}")

# ===== 清理旧项目 =====
if os.path.exists(PROJECT_DIR):
    shutil.rmtree(PROJECT_DIR)
    print("[Clean] 清理旧项目")

# ===== Stage 1: PM Agent =====
print("\n" + "=" * 60)
print("Stage 1: PM Agent 解析")
print("=" * 60)
t0 = time.time()

try:
    from agents.pm_agent import PMAgent
    pm = PMAgent()
    pm_result = pm.parse(REPORT_TEXT)
    t1 = time.time()
    record_stage("PM Agent", t0, t1, True,
                 f"project={pm_result['project_name']}, modules={len(pm_result['modules'])}, score={pm_result.get('_quality', {}).get('score', 'N/A')}")
    print(f"模块列表: {[m['name'] for m in pm_result['modules']]}")
except Exception as e:
    t1 = time.time()
    record_stage("PM Agent", t0, t1, False, str(e))
    print(f"FAILED: {e}")
    sys.exit(1)

# ===== Stage 2: Architect Agent =====
print("\n" + "=" * 60)
print("Stage 2: Architect Agent 设计")
print("=" * 60)
t0 = time.time()

try:
    from agents.architect_agent import ArchitectAgent
    architect = ArchitectAgent()
    arch_result = architect.design(
        project_name=pm_result["project_name"],
        tech_stack="java",
        modules=pm_result["modules"],
        requirements_summary=json.dumps(pm_result, ensure_ascii=False),
    )
    t1 = time.time()
    schema_tables = arch_result["db_schema"].count("CREATE TABLE")
    record_stage("Architect", t0, t1, True,
                 f"tables={schema_tables}, api_paths={arch_result['api_contract'].count('/api/')}")
except Exception as e:
    t1 = time.time()
    record_stage("Architect", t0, t1, False, str(e))
    print(f"FAILED: {e}")
    sys.exit(1)

# ===== Stage 3: Coder Agent (Full Pipeline) =====
print("\n" + "=" * 60)
print("Stage 3: Coder Agent 两阶段生成")
print("=" * 60)
t0 = time.time()

try:
    from agents.coder_agent import CoderAgent
    from tools.project_init import init_project_from_template
    from config import TECH_STACKS

    # 初始化项目（含预置公共类）
    init_project_from_template("java", PROJECT_NAME, PROJECT_DIR)
    print(f"[Init] 项目初始化完成: {PROJECT_DIR}")

    # 保存设计文档
    os.makedirs(PROJECT_DIR, exist_ok=True)
    with open(os.path.join(PROJECT_DIR, "schema.sql"), "w", encoding="utf-8") as f:
        f.write(arch_result["db_schema"])
    with open(os.path.join(PROJECT_DIR, "api.yaml"), "w", encoding="utf-8") as f:
        f.write(arch_result["api_contract"])

    coder = CoderAgent(
        tech_stack="java",
        project_name=PROJECT_NAME,
        db_schema=arch_result["db_schema"],
        api_contract=arch_result["api_contract"],
    )

    code_files = coder.generate_all_modules(pm_result["modules"])
    t1 = time.time()

    # 统计文件
    java_files = [f for f in code_files if f["file_path"].endswith(".java")]
    record_stage("Coder Agent", t0, t1, True,
                 f"total_files={len(code_files)}, java_files={len(java_files)}")
    print(f"生成文件数: {len(code_files)} (Java: {len(java_files)})")

except Exception as e:
    t1 = time.time()
    record_stage("Coder Agent", t0, t1, False, str(e))
    print(f"FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ===== Stage 3.5: Validator Agent 跨文件校验 =====
print("\n" + "=" * 60)
print("Stage 3.5: Validator Agent 跨文件校验")
print("=" * 60)
t0 = time.time()

try:
    from agents.validator_agent import ValidatorAgent
    validator = ValidatorAgent(
        tech_stack="java",
        project_name=PROJECT_NAME,
    )
    val_result = validator.validate_and_fix()
    t1 = time.time()
    record_stage("Validator Agent", t0, t1, val_result["valid"],
                 f"issues={val_result['issues_found']}, fixes={val_result['fixes_applied']}, compile_errors={val_result['compile_errors']}")
    print(f"校验结果: 发现 {val_result['issues_found']} 个问题, 修复 {val_result['fixes_applied']} 处, 剩余编译错误 {val_result['compile_errors']} 个")
except Exception as e:
    t1 = time.time()
    record_stage("Validator Agent", t0, t1, False, str(e))
    print(f"Validator Agent 异常: {e}")
    import traceback
    traceback.print_exc()

# ===== Stage 4: 最终编译验证 =====
print("\n" + "=" * 60)
print("Stage 4: 最终编译验证")
print("=" * 60)
t0 = time.time()

try:
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

    # 保存编译日志
    with open(os.path.join(PROJECT_DIR, "compile_test.log"), "w", encoding="utf-8") as f:
        f.write("STDOUT:\n" + result.stdout + "\n\nSTDERR:\n" + result.stderr)

    record_stage("Compile", t0, t1, success,
                 f"errors={error_count}, returncode={result.returncode}")

    if not success:
        # 提取前 20 个错误
        errors = [line for line in result.stderr.split('\n') if '[ERROR]' in line][:20]
        for e in errors:
            print(f"  ERR: {e[:120]}")

except Exception as e:
    t1 = time.time()
    record_stage("Compile", t0, t1, False, str(e))
    print(f"FAILED: {e}")

# ===== 总结 =====
print("\n" + "=" * 60)
print("测试总结")
print("=" * 60)
total_time = sum(s["duration_sec"] for s in results["stages"].values())
all_success = all(s["success"] for s in results["stages"].values())
print(f"总耗时: {round(total_time, 1)}s")
print(f"全部通过: {all_success}")
for name, data in results["stages"].items():
    status = "OK" if data["success"] else "FAIL"
    print(f"  [{status}] {name}: {data['duration_sec']}s - {data['details']}")

# 保存结果
with open(os.path.join(WORKSPACE, "test_result.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\n结果已保存: {os.path.join(WORKSPACE, 'test_result.json')}")
print(f"编译日志: {os.path.join(PROJECT_DIR, 'compile_test.log')}")
