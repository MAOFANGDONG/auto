"""
LangGraph 全局状态定义
所有 Agent 之间共享的状态，通过 TypedDict 强类型约束
"""
from typing import TypedDict, List, Dict, Optional, Literal, Any
from typing_extensions import Annotated
import operator


class TaskItem(TypedDict):
    """单个任务项"""
    task_id: str
    module_name: str           # 模块名称，如"用户管理"
    description: str           # 任务描述
    task_type: Literal["backend", "frontend", "miniapp", "database"]
    status: Literal["pending", "running", "done", "failed"]
    assigned_agent: str        # 分配的 Agent 名称
    output_files: List[str]    # 生成的文件路径列表
    error_log: Optional[str]   # 错误日志


class CodeFile(TypedDict):
    """生成的代码文件"""
    file_path: str             # 相对路径，如 src/main/java/User.java
    content: str               # 文件内容
    language: str              # 编程语言


class BuildResult(TypedDict):
    """构建验证结果"""
    success: bool
    stage: Literal["compile", "install_deps", "start_service", "health_check"]
    stdout: str
    stderr: str
    fix_attempts: int          # 已尝试修复次数


class AgentState(TypedDict):
    """
    LangGraph 全局状态
    整个流程的所有数据都存这里，Agent 节点读取和修改这个状态
    """
    # 输入阶段
    report_text: str                          # 开题报告原始文本
    report_path: Optional[str]                # 上传的文件路径

    # PM Agent 输出
    tech_stack: Literal["java", "python"]     # 选定的技术栈
    project_name: str                         # 项目名称
    modules: List[Any]                        # 功能模块清单（字符串或包含详细信息的字典）
    requirements_summary: str                 # 需求摘要
    human_approved: bool                      # 人工是否确认过

    # Architect Agent 输出
    db_schema: str                            # 数据库 Schema（SQL）
    api_contract: str                         # OpenAPI 契约（YAML）
    design_approved: bool                     # 设计是否确认过

    # Coder Agent 输出
    code_files: Annotated[List[CodeFile], operator.add]  # 生成的所有代码文件

    # Builder Agent 输出
    build_results: List[BuildResult]          # 构建验证结果
    project_ready: bool                       # 项目是否可交付

    # 全局控制
    current_stage: Literal[
        "idle", "parsing", "waiting_human_req",
        "designing", "waiting_human_design",
        "coding", "building", "fixing", "delivered", "error"
    ]
    error_message: Optional[str]              # 全局错误信息
    logs: Annotated[List[str], operator.add]  # 执行日志（用于前端显示）

    # Git 版本追踪
    git_commits: List[Dict[str, str]]         # 提交历史 [{"hash": "...", "message": "...", "stage": "..."}]
    last_git_commit: Optional[str]            # 最后一次提交的 hash
