"""
ValidatorAgent：代码整合校验器
扫描所有生成的代码，执行跨文件一致性检查并自动修复
"""
import json
import os
import re
from typing import Dict, List, Optional
from loguru import logger

from config import get_agent_model_config, get_llm_client
from prompts.prompt_loader import prompts
from tools.java_indexer import JavaIndex
from tools.consistency_checker import ConsistencyChecker, Issue
from tools.compile_checker import compile_check
from tools.retry_wrapper import retry_with_fallback
from tools.git_manager import commit_on_stage


class ValidatorAgent:
    """代码校验 Agent - 确定性检查 + LLM 修复"""

    def __init__(self, tech_stack: str, project_name: str, model_override: Dict = None):
        config = get_agent_model_config("validator", override=model_override)
        self.llm = get_llm_client(config)
        self.tech_stack = tech_stack
        self.project_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workspace", project_name)
        self.max_iterations = 3

    def validate_and_fix(self) -> Dict:
        """
        主入口：扫描 → 检查 → 修复 → 编译验证（循环）
        :return: {"valid": bool, "issues_found": int, "fixes_applied": int, "compile_errors": int}
        """
        if self.tech_stack != "java":
            logger.info("[ValidatorAgent] 非 Java 项目，跳过校验")
            return {"valid": True, "issues_found": 0, "fixes_applied": 0, "compile_errors": 0}

        total_fixes = 0

        for iteration in range(1, self.max_iterations + 1):
            logger.info(f"[ValidatorAgent] 第 {iteration}/{self.max_iterations} 轮校验...")

            # Step 1: 建立索引
            index = JavaIndex().build(self.project_dir)
            logger.info(f"[ValidatorAgent] 索引建立完成: {index}")

            # Step 2: 一致性检查
            checker = ConsistencyChecker(index)
            issues = checker.check()
            logger.info(f"[ValidatorAgent] 发现问题: {len(issues)} 个")

            # Step 3: 程序自动修复简单问题
            auto_fixed = self._auto_fix_simple_issues(issues, index)
            total_fixes += auto_fixed
            logger.info(f"[ValidatorAgent] 自动修复: {auto_fixed} 个")

            if auto_fixed > 0:
                commit_on_stage(
                    self.project_dir, "validator",
                    f"第{iteration}轮自动修复 ({auto_fixed}处)",
                    {"issues": len(issues), "fixed": auto_fixed}
                )

            if auto_fixed > 0:
                # 重新编译验证自动修复效果
                compile_result = compile_check(self.project_dir, f"compile_validator_{iteration}.log")
                if compile_result["success"]:
                    logger.info(f"[ValidatorAgent] 编译通过 ✓")
                    return {
                        "valid": True,
                        "issues_found": len(issues),
                        "fixes_applied": total_fixes,
                        "compile_errors": 0,
                    }
                # 还有编译错误，继续下一轮
                remaining_errors = compile_result["error_count"]
                logger.info(f"[ValidatorAgent] 仍有 {remaining_errors} 个编译错误")
                if iteration < self.max_iterations:
                    continue

            # Step 4: 如果有复杂问题，调用 LLM 修复
            unresolved = [i for i in issues if i.severity == "error"]
            if unresolved and iteration < self.max_iterations:
                llm_fixed = self._llm_fix_issues(unresolved, index)
                total_fixes += llm_fixed
                logger.info(f"[ValidatorAgent] LLM 修复: {llm_fixed} 个")
                if llm_fixed > 0:
                    commit_on_stage(
                        self.project_dir, "validator",
                        f"第{iteration}轮LLM修复 ({llm_fixed}处)",
                        {"issues": len(unresolved), "fixed": llm_fixed}
                    )
                    continue

            # Step 5: 最终编译验证
            compile_result = compile_check(self.project_dir, f"compile_validator_final.log")
            if compile_result["success"]:
                logger.info(f"[ValidatorAgent] 最终编译通过 ✓")
                return {
                    "valid": True,
                    "issues_found": len(issues),
                    "fixes_applied": total_fixes,
                    "compile_errors": 0,
                }

            logger.warning(f"[ValidatorAgent] 第 {iteration} 轮后仍有编译错误")

        # 超出最大迭代次数
        final_compile = compile_check(self.project_dir, "compile_validator_final.log")
        return {
            "valid": final_compile["success"],
            "issues_found": len(issues) if 'issues' in dir() else 0,
            "fixes_applied": total_fixes,
            "compile_errors": final_compile.get("error_count", 0),
        }

    def _auto_fix_simple_issues(self, issues: List[Issue], index: JavaIndex) -> int:
        """自动修复简单问题，返回修复数量
        
        安全修复：
        1. 补充缺失的接口方法（空实现）
        2. 枚举 .name() 问题（去掉 .name()）
        
        危险修复（已禁用，交给 LLM）：
        - 字段名替换（容易搞错对象类型上下文）
        """
        fixed_count = 0
        for issue in issues:
            if issue.issue_type == "missing_method_impl":
                if self._fix_missing_method(issue, index):
                    fixed_count += 1
            elif issue.issue_type == "enum_type_mismatch":
                if self._fix_enum_mismatch(issue):
                    fixed_count += 1
            # 注意：不自动修复 unresolved_field，因为容易搞错上下文
            # 例如 product.getUserId() 不能被替换成 getBuyerId()
        return fixed_count

    def _fix_missing_method(self, issue: Issue, index: JavaIndex) -> bool:
        """在 ServiceImpl 中补充缺失的接口方法（空实现）"""
        try:
            with open(issue.file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Parse the method signature from message
            # Message format: "XxxServiceImpl 未实现接口 XxxService 的方法: ReturnType methodName(Type param)"
            m = re.search(r'方法:\s*(.+)', issue.message)
            if not m:
                return False
            sig = m.group(1).strip()

            # Extract method info
            mm = re.match(r'(\S+)\s+(\w+)\((.*)\)', sig)
            if not mm:
                return False
            return_type = mm.group(1)
            method_name = mm.group(2)
            params = mm.group(3)

            # Build stub body
            if return_type == 'void':
                body = '        // TODO: 实现业务逻辑\n        throw new UnsupportedOperationException("待实现");'
            elif return_type in ('int', 'long', 'short', 'byte', 'float', 'double'):
                body = f'        // TODO: 实现业务逻辑\n        return 0;'
            elif return_type == 'boolean':
                body = f'        // TODO: 实现业务逻辑\n        return false;'
            elif return_type == 'String':
                body = f'        // TODO: 实现业务逻辑\n        return "";'
            else:
                body = f'        // TODO: 实现业务逻辑\n        return null;'

            stub = f"""\n    @Override\n    public {return_type} {method_name}({params}) {{\n{body}\n    }}\n"""

            # Insert before the last }
            last_brace = content.rfind('}')
            if last_brace > 0:
                content = content[:last_brace] + stub + content[last_brace:]
                with open(issue.file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                logger.info(f"[ValidatorAgent] 自动补充方法: {method_name} in {issue.file_path}")
                return True
        except Exception as e:
            logger.warning(f"[ValidatorAgent] 补充方法失败: {e}")
        return False

    def _fix_enum_mismatch(self, issue: Issue) -> bool:
        """修复枚举类型不匹配"""
        try:
            with open(issue.file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Case 1: Enum.VALUE.name() assigned to enum field -> remove .name()
            new_content = re.sub(r'(\w+)\.(\w+)\.name\(\)', r'\1.\2', content)

            # Case 2: String literal assigned to enum field -> add valueOf
            # This is more complex, skip for auto-fix

            if new_content != content:
                with open(issue.file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                logger.info(f"[ValidatorAgent] 自动修复枚举: {issue.file_path}")
                return True
        except Exception as e:
            logger.warning(f"[ValidatorAgent] 修复枚举失败: {e}")
        return False

    def _fix_field_name_typo(self, issue: Issue, index: JavaIndex) -> bool:
        """尝试修复字段名拼写错误（找相似字段名）"""
        try:
            # Extract field name from message
            m = re.search(r"字段 '(\w+)'", issue.message)
            if not m:
                return False
            wrong_name = m.group(1)

            # Extract class name from message
            cm = re.search(r'(\w+) 中没有字段', issue.message)
            if not cm:
                return False
            class_name = cm.group(1)

            cls = None
            for fqn, c in index.classes.items():
                if c.name == class_name:
                    cls = c
                    break
            if not cls:
                return False

            # Find similar field name
            candidates = [f.name for f in cls.fields]
            similar = self._find_similar_name(wrong_name, candidates, cls.name)
            if similar and similar != wrong_name:
                with open(issue.file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Replace getter/setter references
                pattern = re.compile(r'\b(\w+)\.(get|set)' + re.escape(wrong_name[0].upper() + wrong_name[1:]) + r'\b')
                new_content = pattern.sub(r'\1.\2' + similar[0].upper() + similar[1:], content)

                # Replace direct field references
                pattern2 = re.compile(r'\b' + re.escape(wrong_name) + r'\b')
                new_content = pattern2.sub(similar, new_content)

                if new_content != content:
                    with open(issue.file_path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    logger.info(f"[ValidatorAgent] 自动替换字段: {wrong_name} -> {similar} in {issue.file_path}")
                    return True
        except Exception as e:
            logger.warning(f"[ValidatorAgent] 修复字段失败: {e}")
        return False

    def _find_similar_name(self, target: str, candidates: List[str], cls_name: str = "") -> Optional[str]:
        """找最相似的字段名（单向映射，避免乒乓替换）"""
        if not candidates:
            return None
        # Exact match (case-insensitive)
        for c in candidates:
            if c.lower() == target.lower():
                return c
        # One-way mappings: only map from wrong name to correct name
        # Never map back to avoid ping-pong
        mappings = {
            'price': 'amount',
            'message': 'remark',
            'productTitle': 'title',
        }
        # Context-aware mapping for userId/buyerId/sellerId
        if target == 'userId':
            if 'buyerId' in candidates:
                return 'buyerId'
            if 'sellerId' in candidates:
                return 'sellerId'
        if target in mappings and mappings[target] in candidates:
            return mappings[target]
        return None

    def _llm_fix_issues(self, issues: List[Issue], index: JavaIndex) -> int:
        """调用 LLM 修复复杂问题"""
        if not issues:
            return 0

        # Build issue summary
        issue_summary = []
        for i, issue in enumerate(issues[:20], 1):  # Limit to 20 issues
            issue_summary.append(
                f"{i}. [{issue.issue_type}] {issue.message}\n"
                f"   文件: {issue.file_path}\n"
                f"   建议: {issue.suggestion or 'N/A'}"
            )

        # Extract relevant source snippets
        snippets = self._extract_snippets(issues, index)

        prompt = prompts.load(
            "validator_agent",
            project_dir=self.project_dir,
            issue_count=len(issues),
            issues="\n\n".join(issue_summary),
            snippets=snippets,
        )

        try:
            logger.info("[ValidatorAgent] 调用 LLM 分析不一致问题...")
            response = self.llm.invoke([("user", prompt)])
            fix_plan = self._parse_fix_plan(response.content)

            if not fix_plan.get("need_code_change"):
                return 0

            applied = 0
            for change in fix_plan.get("code_changes", []):
                if self._apply_change(change):
                    applied += 1

            return applied
        except Exception as e:
            logger.warning(f"[ValidatorAgent] LLM 修复异常: {e}")
            return 0

    def _extract_snippets(self, issues: List[Issue], index: JavaIndex) -> str:
        """提取相关代码片段供 LLM 参考"""
        snippets = []
        seen_files = set()

        for issue in issues:
            fp = issue.file_path
            if fp in seen_files or len(seen_files) >= 5:
                continue
            seen_files.add(fp)

            try:
                with open(fp, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                # Extract class declaration and first 30 lines
                lines = content.split('\n')[:40]
                snippets.append(f"=== {os.path.basename(fp)} ===\n" + "\n".join(lines))
            except Exception:
                pass

        return "\n\n".join(snippets)

    def _parse_fix_plan(self, text: str) -> Dict:
        """解析 LLM 返回的修复计划 JSON"""
        try:
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
            logger.warning("[ValidatorAgent] 无法解析修复计划 JSON")
            return {"need_code_change": False, "code_changes": []}

    def _apply_change(self, change: Dict) -> bool:
        """执行单个修复操作"""
        action = change.get("action")
        file_path = change.get("file_path")
        if not file_path:
            return False

        full_path = file_path if os.path.isabs(file_path) else os.path.join(self.project_dir, file_path)
        if not os.path.exists(full_path):
            logger.warning(f"[ValidatorAgent] 文件不存在: {full_path}")
            return False

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()

            original = content

            if action == "replace":
                old = change.get("old_text", "")
                new = change.get("new_text", "")
                if old and old in content:
                    content = content.replace(old, new, 1)

            elif action == "insert_after":
                anchor = change.get("anchor", "")
                new = change.get("new_text", "")
                if anchor and anchor in content:
                    content = content.replace(anchor, anchor + new, 1)

            elif action == "delete":
                old = change.get("old_text", "")
                if old and old in content:
                    content = content.replace(old, "", 1)

            if content != original:
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)
                logger.info(f"[ValidatorAgent] 已修复: {full_path}")
                return True

        except Exception as e:
            logger.error(f"[ValidatorAgent] 修复失败: {e}")

        return False
