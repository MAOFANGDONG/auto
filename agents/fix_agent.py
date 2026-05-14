"""
Fix Agent：编译错误自动修复器
基于 SWE-agent 的 ReAct 循环：读取编译日志 → LLM 分析 → 执行修复
"""
import json
import os
import re
from typing import Dict, List
from loguru import logger

from config import get_agent_model_config, get_llm_client
from prompts.prompt_loader import prompts
from tools.git_manager import GitManager, commit_on_stage


class FixAgent:
    """编译错误修复 Agent"""

    def __init__(self, tech_stack: str, project_name: str, model_override: Dict = None):
        config = get_agent_model_config("builder", override=model_override)
        self.llm = get_llm_client(config)
        self.tech_stack = tech_stack
        self.project_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workspace", project_name)

    def analyze_and_fix(self, build_result: Dict) -> Dict:
        """
        分析编译错误并尝试自动修复
        :param build_result: BuilderAgent 返回的构建结果
        :return: {"fixed": bool, "changes": List[Dict], "message": str}
        """
        stdout = build_result.get("stdout", "")
        stderr = build_result.get("stderr", "")
        stage = build_result.get("stage", "compile")
        command = build_result.get("command", "")

        if not stderr and not stdout:
            return {"fixed": False, "changes": [], "message": "没有错误日志可供分析"}

        # 修复前：暂存当前状态（支持回滚）
        git = GitManager(self.project_dir)
        if git.initialized:
            git.stash(message="修复前自动暂存")

        # 收集项目文件列表
        file_list = self._scan_project_files()

        # 1. 加载 Prompt
        prompt = prompts.load(
            "builder_agent",
            tech_stack=self.tech_stack,
            stage=stage,
            command=command,
            stdout=stdout[:3000],  # 截断防止超长
            stderr=stderr[:5000],  # 错误日志通常更重要
            file_list=file_list,
        )

        # 2. 调用 LLM 分析错误
        logger.info("[Fix Agent] 调用 LLM 分析编译错误...")
        response = self.llm.invoke([("user", prompt)])

        # 3. 解析修复指令
        fix_plan = self._parse_fix_plan(response.content)

        if not fix_plan.get("need_code_change"):
            return {
                "fixed": False,
                "changes": [],
                "message": fix_plan.get("root_cause", "无需代码修改"),
            }

        # 4. 执行修复
        applied_changes = []
        for change in fix_plan.get("code_changes", []):
            success = self._apply_change(change)
            if success:
                applied_changes.append(change)
                logger.info(f"[Fix Agent] 已修复: {change['file_path']}")
            else:
                logger.warning(f"[Fix Agent] 修复失败: {change['file_path']}")

        result = {
            "fixed": len(applied_changes) > 0,
            "changes": applied_changes,
            "message": fix_plan.get("root_cause", "已尝试修复"),
        }

        # 修复后：如果修复成功则提交，否则回滚到修复前状态
        if git.initialized:
            if result["fixed"]:
                commit_on_stage(
                    self.project_dir, "fix",
                    f"自动修复编译错误 ({len(applied_changes)}处)",
                    {"files": [c['file_path'] for c in applied_changes], "root_cause": result['message'][:100]}
                )
            else:
                # 修复未生效，恢复暂存（回滚到修复前状态）
                git.stash_pop()
                logger.info("[Fix Agent] 修复未生效，已回滚到修复前状态")

        return result

    def _parse_fix_plan(self, text: str) -> Dict:
        """解析 LLM 返回的修复计划 JSON"""
        try:
            # 去掉 Markdown 代码块
            cleaned = text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
            return json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            logger.warning("[Fix Agent] 无法解析修复计划 JSON，尝试提取关键信息")
            # Fallback：简单提取 affected_files
            files = re.findall(r'[\w\-]+\.(java|py|xml|yml|yaml|vue|js|ts)', text)
            return {
                "error_type": "unknown",
                "root_cause": text[:200],
                "affected_files": list(set(files)),
                "need_code_change": False,
                "code_changes": [],
            }

    def _scan_project_files(self) -> str:
        """扫描项目中的文件列表，供 LLM 参考"""
        import glob
        files = []
        src_dir = os.path.join(self.project_dir, "src")
        if os.path.exists(src_dir):
            for pattern in ["**/*.java", "**/*.xml", "**/*.yml", "**/*.yaml"]:
                matched = glob.glob(os.path.join(src_dir, pattern), recursive=True)
                for m in sorted(matched):
                    rel = os.path.relpath(m, self.project_dir).replace("\\", "/")
                    files.append(rel)
        return "\n".join(files[:50])  # 限制数量

    def _apply_change(self, change: Dict) -> bool:
        """执行单个修复操作"""
        action = change.get("action")
        file_path = change.get("file_path")
        if not file_path:
            return False

        # 拼接绝对路径
        if not os.path.isabs(file_path):
            full_path = os.path.join(self.project_dir, file_path)
        else:
            full_path = file_path

        if not os.path.exists(full_path):
            logger.warning(f"[Fix Agent] 文件不存在: {full_path}")
            return False

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()

            if action == "replace_import":
                old = change.get("old_text", "")
                new = change.get("new_text", "")
                if old and old in content:
                    content = content.replace(old, new, 1)
                else:
                    return False

            elif action == "modify":
                old = change.get("old_text", "")
                new = change.get("new_text", "")
                if old and old in content:
                    content = content.replace(old, new, 1)
                else:
                    return False

            elif action == "add":
                new = change.get("new_text", "")
                content = content + "\n" + new

            elif action == "delete":
                old = change.get("old_text", "")
                if old and old in content:
                    content = content.replace(old, "", 1)
                else:
                    return False

            else:
                logger.warning(f"[Fix Agent] 未知操作: {action}")
                return False

            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            return True

        except Exception as e:
            logger.error(f"[Fix Agent] 修复失败: {e}")
            return False
