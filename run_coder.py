#!/usr/bin/env python3
"""
独立执行 Coder Agent，带详细进度日志（无缓冲模式）
"""
import json
import os
import sys
import traceback

# 强制无缓冲输出
sys.stdout.reconfigure(line_buffering=True)

from loguru import logger

# 配置日志 - 同步模式确保实时写入
logger.remove()
logger.add(
    "workspace/coder_run.log",
    rotation="10 MB",
    encoding="utf-8",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    enqueue=False,  # 同步模式，后台任务避免异步队列问题
)
logger.add(sys.stdout, level="INFO", enqueue=False)

WORKSPACE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workspace")
PROJECT_NAME = "blindbox_community_platform"

def main():
    project_dir = os.path.join(WORKSPACE_DIR, PROJECT_NAME)

    # 1. 读取 PM 结果
    pm_path = os.path.join(WORKSPACE_DIR, "blindbox_pm_result.json")
    with open(pm_path, "r", encoding="utf-8") as f:
        pm_result = json.load(f)
    modules = pm_result.get("modules", [])
    logger.info(f"[Setup] 加载 PM 结果: {len(modules)} 个模块")

    # 2. 读取 schema + api（并在内存中修复）
    schema_path = os.path.join(project_dir, "schema.sql")
    api_path = os.path.join(project_dir, "api.yaml")
    with open(schema_path, "r", encoding="utf-8") as f:
        db_schema = f.read()
    with open(api_path, "r", encoding="utf-8") as f:
        api_raw = f.read()
    logger.info(f"[Setup] Schema: {len(db_schema)} chars, API raw: {len(api_raw)} chars")

    # 3. 自动修复 API 契约
    from tools.api_repair import repair_api_yaml
    logger.info("[Setup] 自动修复 API 契约...")
    api_contract, repair_report = repair_api_yaml(api_raw, db_schema)
    logger.info(f"[Setup] API 修复: {len(repair_report.get('added_schemas', []))} schemas 已推导")
    if repair_report.get('errors'):
        logger.warning(f"[Setup] API 修复错误: {repair_report['errors']}")

    # 4. 初始化项目模板
    from tools.project_init import init_project_from_template
    logger.info("[Setup] 初始化项目模板...")
    init_project_from_template(
        tech_stack="java",
        project_name=PROJECT_NAME,
        output_dir=project_dir,
    )
    logger.info("[Setup] 模板初始化完成")

    # 4. 初始化 Coder Agent
    from agents.coder_agent import CoderAgent
    coder = CoderAgent(
        tech_stack="java",
        project_name=PROJECT_NAME,
        db_schema=db_schema,
        api_contract=api_contract,
    )

    # 5. 执行生成
    logger.info("=" * 60)
    logger.info("[Coder Agent] 开始生成代码")
    logger.info("=" * 60)

    try:
        code_files = coder.generate_all_modules(modules)
        logger.info("=" * 60)
        logger.info(f"[Coder Agent] 全部完成: {len(code_files)} 个文件")
        logger.info("=" * 60)

        # 统计文件类型
        stats = {}
        for f in code_files:
            path = f.get("file_path", "")
            for layer in ["entity/", "repository/", "service/impl/", "service/", "controller/", "dto/"]:
                if layer in path:
                    stats[layer.rstrip("/")] = stats.get(layer.rstrip("/"), 0) + 1
                    break
        for k, v in sorted(stats.items()):
            logger.info(f"  {k}: {v} 个文件")

    except Exception as e:
        logger.error(f"[Coder Agent] 执行异常: {e}")
        logger.error(traceback.format_exc())
        raise

if __name__ == "__main__":
    main()
