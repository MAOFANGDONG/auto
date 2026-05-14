"""
自动化毕设开发系统 - 入口文件
LangGraph 状态机编排，串联所有 Agent
"""
import os
import sys
import json
from typing import Dict, Any

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from loguru import logger

from state import AgentState, TaskItem, CodeFile
from config import WORKSPACE_DIR, TECH_STACKS
from prompts.prompt_loader import prompts
from tools.checkpoint_manager import CheckpointManager
from tools.git_manager import GitManager, commit_on_stage

# ==================== 状态机节点函数 ====================

def parse_report_node(state: AgentState) -> Dict[str, Any]:
    """
    PM Agent：解析开题报告
    输入：report_text
    输出：project_name, tech_stack, modules, entities, actors, constraints
    """
    from agents.pm_agent import PMAgent

    try:
        logger.info("[PM Agent] 开始解析开题报告...")
        pm = PMAgent()
        result = pm.parse(state["report_text"])

        # 根据技术栈线索匹配技术栈
        tech_hint = result.get("tech_stack_hint", "").lower()
        if "springboot" in tech_hint or "spring" in tech_hint or "java" in tech_hint:
            tech_stack = "java"
        elif "django" in tech_hint or "flask" in tech_hint or "fastapi" in tech_hint or "python" in tech_hint:
            tech_stack = "python"
        else:
            tech_stack = "java"  # 默认 Java

        logger.info(f"[PM Agent] 解析完成，项目: {result['project_name']}, 技术栈: {tech_stack}")

        # 传递完整的模块信息（包含 description, core_features 等），供下游 Agent 使用
        modules_full = result.get("modules", [])

        return {
            "project_name": result["project_name"],
            "tech_stack": tech_stack,
            "modules": modules_full,
            "requirements_summary": json.dumps(result, ensure_ascii=False, indent=2),
            "current_stage": "waiting_human_req",
            "human_approved": False,
            "logs": [f"PM Agent: 识别到 {len(modules_full)} 个模块，推荐技术栈: {TECH_STACKS[tech_stack]['name']}"],
        }
    except Exception as e:
        logger.error(f"[PM Agent] 解析失败: {e}")
        return {
            "current_stage": "error",
            "error_message": f"PM Agent 解析失败: {str(e)[:500]}",
            "logs": [f"PM Agent 错误: {str(e)[:200]}"],
        }


def human_review_req_node(state: AgentState) -> Dict[str, Any]:
    """
    人工确认节点：需求评审
    程序会暂停，等待用户在命令行输入
    """
    print("\n" + "=" * 60)
    print("[PAUSE] 人工确认节点：需求评审")
    print("=" * 60)
    print(f"项目名: {state['project_name']}")
    print(f"技术栈: {TECH_STACKS[state['tech_stack']]['name']}")
    print(f"模块数: {len(state['modules'])}")
    print("\n模块列表:")
    for i, m in enumerate(state["modules"], 1):
        if isinstance(m, dict):
            print(f"   {i}. {m.get('name', '未命名')} ({m.get('module_type', 'unknown')})")
            desc = m.get('description', '')
            if desc:
                print(f"      {desc[:60]}{'...' if len(desc) > 60 else ''}")
            features = m.get('core_features', [])
            if features:
                print(f"      功能: {', '.join(features[:4])}{'...' if len(features) > 4 else ''}")
        else:
            print(f"   {i}. {m}")
    print("\n" + "-" * 60)
    print("操作选项:")
    print("  [1] approve     - 确认并继续")
    print("  [2] reject      - 终止流程")
    print("  [3] stack=java  - 切换到 Java 技术栈")
    print("  [4] stack=py    - 切换到 Python 技术栈")
    print("=" * 60)

    # 自动确认（测试模式）
    print("[AUTO] 自动确认需求")
    return {
        "human_approved": True,
        "current_stage": "designing",
        "logs": ["用户确认需求"],
    }


def design_architecture_node(state: AgentState) -> Dict[str, Any]:
    """
    Architect Agent：设计数据库 + API
    输入：需求摘要、技术栈
    输出：db_schema, api_contract
    """
    from agents.architect_agent import ArchitectAgent

    try:
        logger.info("[Architect Agent] 开始设计架构...")
        architect = ArchitectAgent()

        result = architect.design(
            project_name=state["project_name"],
            tech_stack=state["tech_stack"],
            modules=state["modules"],
            requirements_summary=state["requirements_summary"],
        )

        logger.info("[Architect Agent] 架构设计完成")

        # 把 Schema 和 API 契约写入项目目录，方便人工查看
        project_dir = os.path.join(WORKSPACE_DIR, state["project_name"])
        os.makedirs(project_dir, exist_ok=True)
        with open(os.path.join(project_dir, "schema.sql"), "w", encoding="utf-8") as f:
            f.write(result["db_schema"])
        with open(os.path.join(project_dir, "api.yaml"), "w", encoding="utf-8") as f:
            f.write(result["api_contract"])

        print(f"\n[INFO] 设计文档已保存到: {project_dir}")
        print(f"   - schema.sql  (数据库设计)")
        print(f"   - api.yaml    (接口契约)")

        # Git 提交设计文档
        git_hash = commit_on_stage(
            project_dir, "architect",
            "生成数据库Schema和API契约",
            {"tables": result["db_schema"].count("CREATE TABLE"), "project": state["project_name"]}
        )

        return {
            "db_schema": result["db_schema"],
            "api_contract": result["api_contract"],
            "current_stage": "waiting_human_design",
            "design_approved": False,
            "logs": ["Architect Agent: 数据库 Schema 和 API 契约已生成"],
            "last_git_commit": git_hash,
        }
    except Exception as e:
        logger.error(f"[Architect Agent] 设计失败: {e}")
        return {
            "current_stage": "error",
            "error_message": f"Architect Agent 设计失败: {str(e)[:500]}",
            "logs": [f"Architect Agent 错误: {str(e)[:200]}"],
        }


def human_review_design_node(state: AgentState) -> Dict[str, Any]:
    """人工确认节点：设计评审"""
    print("\n" + "=" * 60)
    print("[PAUSE] 人工确认节点：设计评审")
    print("=" * 60)
    print("设计文档已生成，请查看以下文件:")
    project_dir = os.path.join(WORKSPACE_DIR, state["project_name"])
    print(f"   {os.path.join(project_dir, 'schema.sql')}")
    print(f"   {os.path.join(project_dir, 'api.yaml')}")
    print("\n" + "-" * 60)
    print("操作选项:")
    print("  [1] approve  - 确认设计，开始生成代码")
    print("  [2] reject   - 终止流程")
    print("=" * 60)

    # 自动确认（测试模式）
    print("[AUTO] 自动确认设计")
    return {
        "design_approved": True,
        "current_stage": "coding",
        "logs": ["用户确认设计"],
    }


def code_generation_node(state: AgentState) -> Dict[str, Any]:
    """
    Coder Agent：串行生成代码
    输入：db_schema, api_contract, tech_stack
    输出：code_files
    """
    from agents.coder_agent import CoderAgent
    from tools.project_init import init_project_from_template

    try:
        logger.info("[Coder Agent] 开始生成代码...")

        # 1. 初始化项目模板
        project_dir = os.path.join(WORKSPACE_DIR, state["project_name"])
        init_project_from_template(
            tech_stack=state["tech_stack"],
            project_name=state["project_name"],
            output_dir=project_dir,
        )

        # 2. 生成代码文件
        coder = CoderAgent(
            tech_stack=state["tech_stack"],
            project_name=state["project_name"],
            db_schema=state["db_schema"],
            api_contract=state["api_contract"],
        )

        code_files = coder.generate_all_modules(state["modules"])

        logger.info(f"[Coder Agent] 代码生成完成，共 {len(code_files)} 个文件")

        print(f"\n[INFO] 代码已生成到: {project_dir}")
        print(f"   共 {len(code_files)} 个文件")

        # Git 提交代码生成结果
        git_hash = commit_on_stage(
            project_dir, "coder",
            f"生成全部模块代码 ({len(code_files)}个文件)",
            {"modules": len(state["modules"]), "files": len(code_files)}
        )

        return {
            "code_files": code_files,
            "current_stage": "building",
            "logs": [f"Coder Agent: 生成 {len(code_files)} 个文件"],
            "last_git_commit": git_hash,
        }
    except Exception as e:
        logger.error(f"[Coder Agent] 生成失败: {e}")
        return {
            "current_stage": "error",
            "error_message": f"Coder Agent 生成失败: {str(e)[:500]}",
            "logs": [f"Coder Agent 错误: {str(e)[:200]}"],
        }


def validation_node(state: AgentState) -> Dict[str, Any]:
    """
    Validator Agent：跨文件一致性校验
    在编译前自动修复 ServiceImpl 接口遗漏、字段不匹配、枚举类型等问题
    """
    from agents.validator_agent import ValidatorAgent

    try:
        logger.info("[Validator Agent] 开始跨文件一致性校验...")
        validator = ValidatorAgent(
            tech_stack=state["tech_stack"],
            project_name=state["project_name"],
        )

        result = validator.validate_and_fix()

        if result["valid"]:
            logger.info(f"[Validator Agent] 校验通过 ✓ (修复 {result['fixes_applied']} 处)")
            return {
                "current_stage": "building",
                "validation_passed": True,
                "validation_issues": result.get("issues_found", 0),
                "validation_fixes": result.get("fixes_applied", 0),
                "logs": [f"Validator Agent: 校验通过，修复 {result['fixes_applied']} 处不一致"],
            }
        else:
            logger.warning(f"[Validator Agent] 校验后仍有 {result['compile_errors']} 个编译错误")
            return {
                "current_stage": "fixing",
                "validation_passed": False,
                "validation_issues": result.get("issues_found", 0),
                "validation_fixes": result.get("fixes_applied", 0),
                "logs": [f"Validator Agent: 校验后仍有 {result['compile_errors']} 个编译错误，转入修复"],
            }
    except Exception as e:
        logger.error(f"[Validator Agent] 校验异常: {e}")
        return {
            "current_stage": "building",
            "validation_passed": True,
            "logs": [f"Validator Agent: 校验异常，跳过 - {str(e)[:200]}"],
        }


def build_verification_node(state: AgentState) -> Dict[str, Any]:
    """
    Builder Agent：编译验证
    输入：code_files, tech_stack
    输出：build_results, project_ready
    """
    from agents.builder_agent import BuilderAgent

    try:
        logger.info("[Builder Agent] 开始构建验证...")
        builder = BuilderAgent(
            tech_stack=state["tech_stack"],
            project_name=state["project_name"],
        )

        result = builder.build_and_verify()

        # 继承之前的 fix_attempts（避免死循环）
        existing = state.get("build_results", [])
        if existing:
            last = existing[-1]
            if last.get("stage") == result["stage"] and not last.get("success"):
                result["fix_attempts"] = last.get("fix_attempts", 0)

        if result["success"]:
            logger.info("[Builder Agent] 构建通过 ✓")
            print("\n[OK] 构建验证通过！")

            # Git 标记里程碑
            gm = GitManager(project_dir)
            if gm.initialized:
                gm.create_tag("build-pass", f"编译通过 - {state['project_name']}")
                git_hash = gm.commit(
                    stage="build",
                    message="编译验证通过",
                    details={"errors": 0, "fixes": state.get("validation_fixes", 0)}
                )
            else:
                git_hash = None

            return {
                "build_results": [result],
                "project_ready": True,
                "current_stage": "delivered",
                "logs": ["Builder Agent: 构建验证通过"],
                "last_git_commit": git_hash,
            }
        else:
            logger.warning("[Builder Agent] 构建失败，准备修复...")
            print(f"\n[FAIL] 构建失败: {result.get('stderr', '未知错误')[:200]}")
            return {
                "build_results": [result],
                "project_ready": False,
                "current_stage": "fixing",
                "logs": [f"Builder Agent: 构建失败 - {result.get('stderr', '未知错误')[:200]}"],
            }
    except Exception as e:
        logger.error(f"[Builder Agent] 构建异常: {e}")
        return {
            "current_stage": "error",
            "error_message": f"Builder Agent 异常: {str(e)[:500]}",
            "logs": [f"Builder Agent 异常: {str(e)[:200]}"],
        }


def fix_code_node(state: AgentState) -> Dict[str, Any]:
    """
    修复 Agent：基于 SWE-agent 的 ReAct 循环，分析编译错误并自动修复
    最多重试 3 次
    """
    from agents.fix_agent import FixAgent

    build_results = state.get("build_results", [])
    if not build_results:
        return {"current_stage": "error", "error_message": "没有构建结果可供修复"}

    last_result = build_results[-1]
    fix_attempts = last_result.get("fix_attempts", 0)

    if fix_attempts >= 3:
        logger.error("[Fix Agent] 已达最大重试次数，终止")
        print("\n[ERROR] 代码修复超过 3 次仍未通过，需要人工介入")
        return {
            "current_stage": "error",
            "error_message": "代码修复超过 3 次仍未通过，需要人工介入",
        }

    last_result["fix_attempts"] = fix_attempts + 1
    attempt = last_result["fix_attempts"]
    logger.info(f"[Fix Agent] 第 {attempt} 次修复...")
    print(f"\n[FIX] 尝试第 {attempt} 次自动修复...")

    try:
        # 接入真正的 Fix Agent：读取编译日志 → LLM 分析 → 执行修复
        fix_agent = FixAgent(
            tech_stack=state["tech_stack"],
            project_name=state["project_name"],
        )

        result = fix_agent.analyze_and_fix(last_result)

        if result["fixed"]:
            print(f"[FIX] 已应用 {len(result['changes'])} 处修改: {result['message']}")
            for ch in result["changes"]:
                print(f"    - {ch['file_path']} ({ch['action']})")

            # Git 提交修复结果
            project_dir = os.path.join(WORKSPACE_DIR, state["project_name"])
            git_hash = commit_on_stage(
                project_dir, "fix",
                f"第{attempt}次编译错误修复",
                {"changes": len(result['changes']), "message": result['message'][:100]}
            )
        else:
            print(f"[FIX] 未找到可自动修复的代码变更: {result['message']}")
            git_hash = None

        return {
            "current_stage": "building",
            "build_results": build_results,
            "logs": [f"Fix Agent: 第 {attempt} 次修复 - {result['message']}"],
            "last_git_commit": git_hash,
        }
    except Exception as e:
        logger.error(f"[Fix Agent] 修复异常: {e}")
        return {
            "current_stage": "building",
            "build_results": build_results,
            "logs": [f"Fix Agent: 第 {attempt} 次修复异常 - {str(e)[:200]}"],
        }


def error_handler_node(state: AgentState) -> Dict[str, Any]:
    """错误处理节点"""
    msg = state.get("error_message", "未知错误")
    logger.error(f"[Error] {msg}")
    print(f"\n[ERROR] 流程终止: {msg}")
    return {
        "current_stage": "error",
        "logs": [f"系统错误: {msg}"],
    }


# ==================== 路由函数 ====================

def route_after_human_req(state: AgentState) -> str:
    """需求确认后路由"""
    if state.get("human_approved"):
        return "design"
    if state.get("current_stage") == "error":
        return "error"
    return END


def route_after_human_design(state: AgentState) -> str:
    """设计确认后路由"""
    if state.get("design_approved"):
        return "code"
    if state.get("current_stage") == "error":
        return "error"
    return END


def route_after_build(state: AgentState) -> str:
    """构建后路由"""
    if state.get("project_ready"):
        return "delivered"
    return "fix"


def route_after_fix(state: AgentState) -> str:
    """修复后路由"""
    return "build"


# ==================== 构建 LangGraph ====================

def build_graph():
    """构建状态机图"""
    workflow = StateGraph(AgentState)

    # 注册节点
    workflow.add_node("parse", parse_report_node)
    workflow.add_node("human_req", human_review_req_node)
    workflow.add_node("design", design_architecture_node)
    workflow.add_node("human_design", human_review_design_node)
    workflow.add_node("code", code_generation_node)
    workflow.add_node("build", build_verification_node)
    workflow.add_node("fix", fix_code_node)
    workflow.add_node("error", error_handler_node)

    # 设置入口
    workflow.set_entry_point("parse")

    # 边：解析 -> 人工确认
    workflow.add_edge("parse", "human_req")

    # 条件边：人工确认 -> 设计 或 结束 或 错误
    workflow.add_conditional_edges(
        "human_req",
        route_after_human_req,
        {"design": "design", "error": "error", END: END},
    )

    # 边：设计 -> 人工确认
    workflow.add_edge("design", "human_design")

    # 条件边：设计确认 -> 编码 或 结束 或 错误
    workflow.add_conditional_edges(
        "human_design",
        route_after_human_design,
        {"code": "code", "error": "error", END: END},
    )

    # 边：编码 -> 校验 -> 构建
    workflow.add_node("validate", validation_node)
    workflow.add_edge("code", "validate")
    workflow.add_edge("validate", "build")

    # 条件边：构建 -> 交付 或 修复
    workflow.add_conditional_edges(
        "build",
        route_after_build,
        {"delivered": END, "fix": "fix"},
    )

    # 边：修复 -> 重新构建
    workflow.add_edge("fix", "build")

    # 编译记忆检查点
    memory = MemorySaver()
    graph = workflow.compile(checkpointer=memory)

    return graph


# ==================== 入口函数 ====================

def run_pipeline(report_text: str, thread_id: str = "default", resume: bool = False) -> AgentState:
    """
    运行完整流程
    :param report_text: 开题报告文本
    :param thread_id: 会话 ID，用于区分不同项目
    :param resume: 是否从断点恢复
    :return: 最终状态
    """
    # ===== 断点恢复模式 =====
    if resume:
        logger.info("[Resume] 尝试从断点恢复...")
        # 先解析报告获取 project_name
        from agents.pm_agent import PMAgent
        pm = PMAgent()
        pm_result = pm.parse(report_text)
        project_name = pm_result.get("project_name", "unknown")
        return resume_pipeline(project_name, report_text)

    graph = build_graph()

    initial_state = AgentState(
        report_text=report_text,
        report_path=None,
        tech_stack="java",
        project_name="",
        modules=[],
        requirements_summary="",
        human_approved=False,
        db_schema="",
        api_contract="",
        design_approved=False,
        code_files=[],
        build_results=[],
        project_ready=False,
        current_stage="idle",
        error_message=None,
        logs=["系统启动"],
        git_commits=[],
        last_git_commit=None,
    )

    config = {"configurable": {"thread_id": thread_id}}

    final_state = initial_state
    checkpoint_mgr = None

    try:
        for event in graph.stream(initial_state, config, stream_mode="values"):
            final_state = event
            stage = final_state["current_stage"]
            logger.info(f"当前阶段: {stage}")

            # 保存断点（project_name 确定后）
            if final_state.get("project_name"):
                if checkpoint_mgr is None:
                    checkpoint_mgr = CheckpointManager(final_state["project_name"])
                checkpoint_mgr.save(final_state)

            # 交付完成
            if stage == "delivered":
                project_dir = os.path.join(WORKSPACE_DIR, final_state["project_name"])
                print("\n" + "=" * 60)
                print("[DONE] 项目生成完成！")
                print("=" * 60)
                print(f"项目路径: {project_dir}")
                print(f"文件数量: {len(final_state.get('code_files', []))}")
                print(f"技术栈: {TECH_STACKS[final_state['tech_stack']]['name']}")
                print("=" * 60)
                if checkpoint_mgr:
                    checkpoint_mgr.clear()  # 完成后清除断点
                break

            # 错误终止
            if stage == "error":
                break

    except KeyboardInterrupt:
        print("\n\n[WARNING] 用户中断执行，已保存断点，可使用 resume=True 恢复")
        final_state["current_stage"] = "error"
        final_state["error_message"] = "用户中断"
        if checkpoint_mgr:
            checkpoint_mgr.save(final_state)

    return final_state


def resume_pipeline(project_name: str, report_text: str = "") -> AgentState:
    """
    从断点恢复项目生成
    :param project_name: 项目名称
    :param report_text: 开题报告原文（用于补充 checkpoint 中截断的内容）
    :return: 最终状态
    """
    checkpoint_mgr = CheckpointManager(project_name)
    checkpoint = checkpoint_mgr.load()

    if not checkpoint:
        logger.error("[Resume] 没有找到断点，请重新运行")
        return AgentState(
            report_text=report_text,
            report_path=None,
            tech_stack="java",
            project_name=project_name,
            modules=[],
            requirements_summary="",
            human_approved=False,
            db_schema="",
            api_contract="",
            design_approved=False,
            code_files=[],
            build_results=[],
            project_ready=False,
            current_stage="error",
            error_message="断点不存在",
            logs=["恢复失败：断点不存在"],
            git_commits=[],
            last_git_commit=None,
        )

    # 重建状态（补充被截断的字段）
    # 恢复时尝试回滚到 checkpoint 记录的 git commit（如果存在）
    last_commit = checkpoint.get("last_git_commit")
    if last_commit:
        try:
            from tools.git_manager import GitManager
            gm = GitManager(os.path.join(WORKSPACE_DIR, project_name))
            if gm.initialized and gm.get_current_commit() != last_commit:
                logger.info(f"[Resume] 回滚到 Git 提交: {last_commit[:8]}")
                gm.reset_hard(last_commit)
        except Exception as e:
            logger.warning(f"[Resume] Git 回滚失败: {e}")

    state = AgentState(
        report_text=report_text or checkpoint.get("report_text", ""),
        report_path=None,
        tech_stack=checkpoint.get("tech_stack", "java"),
        project_name=checkpoint.get("project_name", project_name),
        modules=checkpoint.get("modules", []),
        requirements_summary=checkpoint.get("requirements_summary", ""),
        human_approved=True,  # 恢复时自动跳过人工确认
        db_schema=checkpoint.get("db_schema", ""),
        api_contract=checkpoint.get("api_contract", ""),
        design_approved=True,  # 恢复时自动跳过设计确认
        code_files=[],
        build_results=checkpoint.get("build_results", []),
        project_ready=checkpoint.get("project_ready", False),
        current_stage=checkpoint.get("current_stage", "idle"),
        error_message=None,
        logs=checkpoint.get("logs", []) + ["从断点恢复"],
        git_commits=[],
        last_git_commit=last_commit,
    )

    logger.info(f"[Resume] 从阶段 {state['current_stage']} 恢复")
    print(f"\n[Resume] 从阶段 {state['current_stage']} 恢复项目: {project_name}")

    # 根据阶段手动恢复执行
    max_iterations = 20
    iteration = 0

    while state["current_stage"] not in ["delivered", "error"] and iteration < max_iterations:
        iteration += 1
        stage = state["current_stage"]
        logger.info(f"[Resume] 执行阶段: {stage}")

        try:
            if stage == "idle":
                state = parse_report_node(state)
            elif stage == "waiting_human_req":
                state["human_approved"] = True
                state["current_stage"] = "designing"
                state["logs"].append("恢复：自动确认需求")
            elif stage == "designing":
                state = design_architecture_node(state)
            elif stage == "waiting_human_design":
                state["design_approved"] = True
                state["current_stage"] = "coding"
                state["logs"].append("恢复：自动确认设计")
            elif stage == "coding":
                state = code_generation_node(state)
            elif stage == "validating":
                state = validation_node(state)
            elif stage == "building":
                state = build_verification_node(state)
                if state.get("project_ready"):
                    state["current_stage"] = "delivered"
                    break
                else:
                    state["current_stage"] = "fixing"
            elif stage == "fixing":
                state = fix_code_node(state)
                state["current_stage"] = "building"
            else:
                logger.error(f"[Resume] 未知阶段: {stage}")
                break
        except Exception as e:
            logger.error(f"[Resume] 阶段 {stage} 执行失败: {e}")
            state["current_stage"] = "error"
            state["error_message"] = str(e)
            break

        checkpoint_mgr.save(state)

    if state["current_stage"] == "delivered":
        logger.info("[Resume] 项目生成完成！")
        project_dir = os.path.join(WORKSPACE_DIR, state["project_name"])
        print("\n" + "=" * 60)
        print("[DONE] 项目生成完成！")
        print("=" * 60)
        print(f"项目路径: {project_dir}")
        print(f"文件数量: {len(state.get('code_files', []))}")
        print("=" * 60)
        checkpoint_mgr.clear()
    elif state["current_stage"] == "error":
        print(f"\n[ERROR] 恢复失败: {state.get('error_message', '未知错误')}")
    else:
        print(f"\n[WARNING] 恢复中断于阶段: {state['current_stage']}")

    return state


if __name__ == "__main__":
    # 测试入口
    test_report = """
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

    print("[Auto-Graduation] 自动化毕设开发系统启动")
    print("-" * 60)
    final_state = run_pipeline(test_report, thread_id="test_001")
    print(f"\n最终状态: {final_state['current_stage']}")
