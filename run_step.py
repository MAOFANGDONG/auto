"""
分段跑 Pipeline，支持断点恢复
用法: python run_step.py --step 1    # 跑 PM + Architect
       python run_step.py --step 2    # 跑 Coder Phase 1
       python run_step.py --step 3    # 跑 Coder Phase 2
       python run_step.py --step 4    # 跑编译验证
       python run_step.py --step all  # 顺序跑全部
"""
import os
import sys
import json
import time
import shutil
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["LANGCHAIN_PYDANTIC_V2"] = "true"

from loguru import logger

PROJECT_NAME = "personal_ledger"
WORKSPACE = r"C:\Users\20160\auto-graduation\workspace"
PROJECT_DIR = os.path.join(WORKSPACE, PROJECT_NAME)
CHECKPOINT_FILE = os.path.join(WORKSPACE, f"{PROJECT_NAME}_checkpoint.json")

REPORT_TEXT = """
基于SpringBoot的个人记账本管理系统设计与实现

一、项目背景
随着个人理财意识的增强，人们对日常收支管理的需求日益迫切。本系统旨在为用户提供一个简洁、高效的个人记账工具，帮助用户清晰掌握财务状况。

二、系统功能
1. 用户管理：用户注册、登录、个人信息管理
2. 分类管理：收入/支出分类的增删改查（如餐饮、交通、购物、工资等）
3. 账单记录：记录每笔收入或支出（金额、分类、类型、备注、日期）
4. 统计报表：按月统计收支总额、按分类统计占比
5. 数据查询：支持按日期范围、分类、类型筛选账单记录

三、技术选型
后端采用 SpringBoot 3.x + Spring Data JPA + MySQL
前端采用 Vue3 + Element Plus
移动端采用微信小程序

四、性能要求
系统响应时间不超过 2 秒，支持单用户日常记账场景。
"""


def save_checkpoint(data: dict):
    os.makedirs(PROJECT_DIR, exist_ok=True)
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_checkpoint() -> dict:
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def step1_pm_architect():
    """Step 1: PM + Architect"""
    print("=" * 60)
    print("Step 1: PM Agent + Architect Agent")
    print("=" * 60)

    ck = load_checkpoint()
    if ck.get("step1_complete"):
        print("[Skip] Step 1 已完成")
        return

    # 清理旧项目
    if os.path.exists(PROJECT_DIR):
        shutil.rmtree(PROJECT_DIR)
    os.makedirs(PROJECT_DIR, exist_ok=True)

    t0 = time.time()

    # PM
    print("\n[1/2] PM Agent...")
    from agents.pm_agent import PMAgent
    pm = PMAgent()
    pm_result = pm.parse(REPORT_TEXT)
    print(f"  项目: {pm_result['project_name']}, 模块: {len(pm_result['modules'])}")

    # Architect
    print("\n[2/2] Architect Agent...")
    from agents.architect_agent import ArchitectAgent
    architect = ArchitectAgent()
    arch_result = architect.design(
        project_name=pm_result["project_name"],
        tech_stack="java",
        modules=pm_result["modules"],
        requirements_summary=json.dumps(pm_result, ensure_ascii=False),
    )
    t1 = time.time()

    # 保存
    with open(os.path.join(PROJECT_DIR, "schema.sql"), "w", encoding="utf-8") as f:
        f.write(arch_result["db_schema"])
    with open(os.path.join(PROJECT_DIR, "api.yaml"), "w", encoding="utf-8") as f:
        f.write(arch_result["api_contract"])
    with open(os.path.join(PROJECT_DIR, "module_plan.txt"), "w", encoding="utf-8") as f:
        f.write(arch_result.get("module_plan", ""))
    with open(os.path.join(PROJECT_DIR, "pm_result.json"), "w", encoding="utf-8") as f:
        json.dump(pm_result, f, ensure_ascii=False, indent=2)

    schema_tables = arch_result["db_schema"].count("CREATE TABLE")
    api_ops = len([l for l in arch_result["api_contract"].split('\n') if 'operationId' in l])
    module_plan = arch_result.get("module_plan", "")
    has_plan = bool(module_plan.strip())

    print(f"\n  耗时: {t1-t0:.1f}s")
    print(f"  表数: {schema_tables}")
    print(f"  operationId: {api_ops}")
    print(f"  MODULE_PLAN: {'有' if has_plan else '无'} ({len(module_plan)} 字符)")
    if has_plan:
        print(f"\n  Module Plan 预览:")
        print(module_plan[:1500])
        print("  ...")

    save_checkpoint({
        "step1_complete": True,
        "project_name": pm_result["project_name"],
        "tech_stack": "java",
        "modules": pm_result["modules"],
        "db_schema": arch_result["db_schema"],
        "api_contract": arch_result["api_contract"],
        "module_plan": module_plan,
    })


def step2_coder_phase1():
    """Step 2: Coder Phase 1 (Skeleton)"""
    print("=" * 60)
    print("Step 2: Coder Agent Phase 1 (骨架)")
    print("=" * 60)

    ck = load_checkpoint()
    if not ck.get("step1_complete"):
        print("[Error] 请先跑 Step 1")
        return
    if ck.get("step2_complete"):
        print("[Skip] Step 2 已完成")
        return

    from tools.project_init import init_project_from_template
    from agents.coder_agent import CoderAgent

    # 初始化项目模板
    init_project_from_template("java", PROJECT_NAME, PROJECT_DIR)
    print(f"[Init] 项目初始化完成")

    # 保存设计文档
    with open(os.path.join(PROJECT_DIR, "schema.sql"), "w", encoding="utf-8") as f:
        f.write(ck["db_schema"])
    with open(os.path.join(PROJECT_DIR, "api.yaml"), "w", encoding="utf-8") as f:
        f.write(ck["api_contract"])

    coder = CoderAgent(
        tech_stack="java",
        project_name=PROJECT_NAME,
        db_schema=ck["db_schema"],
        api_contract=ck["api_contract"],
    )

    t0 = time.time()
    code_files = coder.generate_all_modules(ck["modules"])
    t1 = time.time()

    # 只统计 Phase 1 的文件（没有 impl/ 和 controller/ 的）
    phase1_files = [f for f in code_files if "service/impl/" not in f["file_path"] and "controller/" not in f["file_path"]]
    print(f"\n  生成文件: {len(code_files)} (Phase 1: {len(phase1_files)})")
    print(f"  耗时: {t1-t0:.1f}s")

    # 统计 Java 文件
    java_files = [f for f in code_files if f["file_path"].endswith(".java")]
    print(f"  Java 文件: {len(java_files)}")

    save_checkpoint({**ck, "step2_complete": True, "total_files": len(code_files)})


def step3_coder_phase2():
    """Step 3: Coder Phase 2 (Implementation) - 从断点继续"""
    print("=" * 60)
    print("Step 3: Coder Agent Phase 2 (实现)")
    print("=" * 60)

    ck = load_checkpoint()
    if not ck.get("step2_complete"):
        print("[Error] 请先跑 Step 2")
        return

    from agents.coder_agent import CoderAgent
    from config import TECH_STACKS
    from prompts.prompt_loader import prompts

    coder = CoderAgent(
        tech_stack="java",
        project_name=PROJECT_NAME,
        db_schema=ck["db_schema"],
        api_contract=ck["api_contract"],
    )

    # 从磁盘读取已生成的 Phase 1 文件构建契约池
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

    system_prompt = prompts.load(
        "coder_system",
        tech_stack_name=TECH_STACKS["java"]["name"],
        project_name_lower=coder.project_name_safe,
    )

    modules = ck["modules"]
    total_impl = 0
    t0_total = time.time()

    for i, module in enumerate(modules):
        module_name, module_info = coder._normalize_module(module, i)

        # 检查是否已有 ServiceImpl
        expected_impl = f"service/impl/{module_name.replace(' ', '')}ServiceImpl.java"
        # 也检查其他可能的命名
        import glob
        existing_impls = glob.glob(os.path.join(src_dir, "service/impl/*.java"))
        existing_controllers = glob.glob(os.path.join(src_dir, "controller/*.java"))

        # 简单的存在性检查：看当前模块名相关的文件是否已存在
        module_key = module_name.replace(' ', '').replace('与', '').replace('管理', '').lower()
        has_impl = any(module_key in os.path.basename(f).lower() for f in existing_impls)
        has_controller = any(module_key in os.path.basename(f).lower() for f in existing_controllers)

        if has_impl and has_controller:
            print(f"[Skip] {module_name} 实现已存在")
            continue

        print(f"\n[Phase 2] {i+1}/{len(modules)}: {module_name}")
        t0 = time.time()

        contract_hint = coder._extract_contracts(contract_pool) if contract_pool else ""
        existing_paths = [f["file_path"] for f in contract_pool]
        preset_hint = coder._get_preset_hint()
        module_plan_hint = coder._extract_module_plan(module_name, module_info)

        try:
            files = coder._generate_phase2(
                module_name, module_info, system_prompt,
                existing_files=existing_paths,
                contract_hint=contract_hint + "\n\n" + preset_hint,
                module_plan_hint=module_plan_hint,
            )
            t1 = time.time()
            print(f"  完成: {len(files)} 个文件, {t1-t0:.1f}s")
            total_impl += len(files)

            for f in files:
                if any(x in f["file_path"] for x in ["service/impl/", "controller/"]):
                    contract_pool.append(f)
        except Exception as e:
            print(f"  失败: {e}")

    t1_total = time.time()
    print(f"\n  Phase 2 总计: {total_impl} 个文件, {t1_total-t0_total:.1f}s")

    save_checkpoint({**ck, "step3_complete": True, "impl_files": total_impl})


def step4_compile():
    """Step 4: 编译验证"""
    print("=" * 60)
    print("Step 4: 编译验证")
    print("=" * 60)

    ck = load_checkpoint()
    if not ck.get("step3_complete") and not ck.get("step2_complete"):
        print("[Error] 请先跑 Step 2 或 3")
        return

    import subprocess
    mvnw = os.path.join(PROJECT_DIR, "mvnw.cmd")
    mvn = "mvn" if shutil.which("mvn") else mvnw

    t0 = time.time()
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

    log_file = os.path.join(PROJECT_DIR, "compile_final.log")
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("STDOUT:\n" + (result.stdout or "") + "\n\nSTDERR:\n" + (result.stderr or ""))

    print(f"  耗时: {t1-t0:.1f}s")
    print(f"  结果: {'通过 [OK]' if success else '失败 [FAIL]'}")
    print(f"  错误数: {error_count}")

    if not success and error_count > 0:
        # 统计每个文件的错误数
        import re
        file_errors = {}
        for line in result.stderr.split('\n'):
            match = re.search(r'\[ERROR\] /C:.+src/main/java/(.+\.java):', line)
            if match:
                fname = match.group(1)
                file_errors[fname] = file_errors.get(fname, 0) + 1

        print(f"\n  错误分布:")
        for fname, count in sorted(file_errors.items(), key=lambda x: -x[1])[:15]:
            print(f"    {count:3d}  {fname}")

    save_checkpoint({**ck, "step4_complete": True, "compile_success": success, "compile_errors": error_count})

    print(f"\n  日志: {log_file}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", choices=["1", "2", "3", "4", "all"], required=True)
    args = parser.parse_args()

    if args.step == "1":
        step1_pm_architect()
    elif args.step == "2":
        step2_coder_phase1()
    elif args.step == "3":
        step3_coder_phase2()
    elif args.step == "4":
        step4_compile()
    elif args.step == "all":
        step1_pm_architect()
        step2_coder_phase1()
        step3_coder_phase2()
        step4_compile()


if __name__ == "__main__":
    main()
