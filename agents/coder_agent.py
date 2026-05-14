"""
Coder Agent：代码生成器（v2 两阶段生成）

架构：
  Phase 1: 生成骨架（Entity + Repository + Service接口 + DTO）
  Phase 1.5: 编译验证骨架
  Phase 2: 生成实现（ServiceImpl + Controller）

关键改进：
1. 模板预置公共类（PageResult/Result/JwtUtil/BaseEntity），消除多版本问题
2. Phase 1 先生成所有 Service 接口，Phase 2 只能实现不能新增方法
3. 契约注入增强：提取 Service 接口完整方法签名
"""
import os
import subprocess
import sys
from typing import List, Dict, Any
from loguru import logger

from config import get_agent_model_config, get_llm_client, WORKSPACE_DIR, TECH_STACKS
from prompts.prompt_loader import prompts
from tools.file_writer import safe_write_file
from tools.retry_wrapper import retry_with_fallback
from tools.git_manager import commit_on_stage


class CoderAgent:
    """代码生成 Agent - v2 两阶段版"""

    # 模板预置的公共类（初始化时已存在于项目中，Coder 不应重复生成）
    PRESET_CLASSES = [
        "src/main/java/com/example/{pkg}/common/Result.java",
        "src/main/java/com/example/{pkg}/common/PageResult.java",
        "src/main/java/com/example/{pkg}/util/JwtUtil.java",
        "src/main/java/com/example/{pkg}/entity/BaseEntity.java",
        "src/main/java/com/example/{pkg}/exception/BusinessException.java",
    ]

    def __init__(
        self,
        tech_stack: str,
        project_name: str,
        db_schema: str,
        api_contract: str,
        model_override: Dict = None,
    ):
        config = get_agent_model_config("coder", override=model_override)
        self.llm = get_llm_client(config)
        self.tech_stack = tech_stack
        self.project_name = project_name
        self.db_schema = db_schema
        self.api_contract = api_contract
        self.project_dir = os.path.join(WORKSPACE_DIR, project_name)
        self.project_name_safe = project_name.lower().replace(" ", "_").replace("-", "_")

        logger.info(f"[Coder Agent] 初始化，技术栈: {tech_stack}")

    def generate_all_modules(self, modules: List[Any]) -> List[Dict]:
        """
        两阶段生成所有模块代码
        :return: 所有生成的文件列表
        """
        all_files = []

        # 加载系统提示词
        system_prompt = prompts.load(
            "coder_system",
            tech_stack_name=TECH_STACKS[self.tech_stack]["name"],
            project_name_lower=self.project_name_safe,
        )

        # ===== Phase 1: 生成骨架（Entity + Repository + Service接口 + DTO）=====
        logger.info("=" * 60)
        logger.info("[Coder Agent] Phase 1: 生成模块骨架")
        logger.info("=" * 60)

        skeleton_files = []
        contract_pool = []  # 契约池，初始为空（模板类已在磁盘上）

        for i, module in enumerate(modules):
            module_name, module_info = self._normalize_module(module, i)
            logger.info(f"[Phase 1] {i+1}/{len(modules)}: {module_name}")

            contract_hint = self._extract_contracts(contract_pool) if contract_pool else ""
            existing_paths = [f["file_path"] for f in contract_pool]

            module_plan_hint = self._extract_module_plan(module_name, module_info)

            files = self._generate_phase1(
                module_name, module_info, system_prompt,
                existing_files=existing_paths,
                contract_hint=contract_hint,
                module_plan_hint=module_plan_hint,
            )
            skeleton_files.extend(files)

            # 将骨架文件加入契约池
            for f in files:
                if any(x in f["file_path"] for x in [
                    "entity/", "repository/", "dto/", "service/"
                ]):
                    contract_pool.append(f)

            logger.info(f"[Phase 1] {module_name} 完成: {len(files)} 个文件")

        all_files.extend(skeleton_files)
        logger.info(f"[Phase 1] 总计: {len(skeleton_files)} 个骨架文件")

        # Git 提交 Phase 1 骨架
        commit_on_stage(
            self.project_dir, "coder",
            f"Phase1 生成模块骨架 ({len(skeleton_files)}个文件)",
            {"modules": len(modules), "files": len(skeleton_files)}
        )

        # ===== Phase 1.5: 编译验证骨架 =====
        if self.tech_stack == "java":
            logger.info("[Phase 1.5] 编译验证骨架...")
            compile_result = self._compile_check()
            if compile_result["success"]:
                logger.info("[Phase 1.5] 骨架编译通过 ✓")
            else:
                err_count = compile_result.get("error_count", 0)
                logger.warning(f"[Phase 1.5] 骨架编译失败: {err_count} 个错误，日志已保存到 compile_phase1.log")
                # 尝试一次自动修复
                if err_count > 0:
                    try:
                        from agents.fix_agent import FixAgent
                        fix_agent = FixAgent(tech_stack=self.tech_stack, project_name=self.project_name)
                        fix_result = fix_agent.analyze_and_fix(compile_result)
                        if fix_result.get("fixed"):
                            logger.info(f"[Phase 1.5] 自动修复已应用 {len(fix_result.get('changes', []))} 处修改")
                            # 再次编译验证
                            compile_result = self._compile_check()
                            if compile_result["success"]:
                                logger.info("[Phase 1.5] 修复后编译通过 ✓")
                            else:
                                logger.warning(f"[Phase 1.5] 修复后仍有 {compile_result.get('error_count', 0)} 个错误，继续 Phase 2")
                        else:
                            logger.warning(f"[Phase 1.5] 自动修复未成功: {fix_result.get('message', '')}")
                    except Exception as e:
                        logger.warning(f"[Phase 1.5] 自动修复异常: {e}")

        # ===== Phase 2: 生成业务实现（ServiceImpl + Controller）=====
        logger.info("=" * 60)
        logger.info("[Coder Agent] Phase 2: 生成业务实现")
        logger.info("=" * 60)

        impl_files = []
        for i, module in enumerate(modules):
            module_name, module_info = self._normalize_module(module, i)
            logger.info(f"[Phase 2] {i+1}/{len(modules)}: {module_name}")

            # Phase 2 的契约注入包含所有骨架文件
            contract_hint = self._extract_contracts(contract_pool) if contract_pool else ""
            existing_paths = [f["file_path"] for f in contract_pool]

            # 额外加入预置类提示
            preset_hint = self._get_preset_hint()

            module_plan_hint = self._extract_module_plan(module_name, module_info)

            files = self._generate_phase2(
                module_name, module_info, system_prompt,
                existing_files=existing_paths,
                contract_hint=contract_hint + "\n\n" + preset_hint,
                module_plan_hint=module_plan_hint,
            )
            impl_files.extend(files)

            # 将实现文件也加入契约池（但优先级低）
            for f in files:
                if any(x in f["file_path"] for x in [
                    "service/impl/", "controller/"
                ]):
                    contract_pool.append(f)

            logger.info(f"[Phase 2] {module_name} 完成: {len(files)} 个文件")

        all_files.extend(impl_files)
        logger.info(f"[Phase 2] 总计: {len(impl_files)} 个实现文件")

        # Git 提交 Phase 2 实现
        commit_on_stage(
            self.project_dir, "coder",
            f"Phase2 生成业务实现 ({len(impl_files)}个文件)",
            {"modules": len(modules), "files": len(impl_files)}
        )

        # ===== 后处理 =====
        if self.tech_stack == "java":
            self._post_process_java_files()

        logger.info(f"[Coder Agent] 全部生成完成: {len(all_files)} 个文件")
        return all_files

    def _extract_module_plan(self, module_name: str, module_info: dict) -> str:
        """从 api_contract + db_schema 中提取当前模块的开发计划"""
        try:
            from tools.contract_extractor import extract_module_contracts
            contracts = extract_module_contracts(self.api_contract, self.db_schema, [module_info])
            return contracts.get(module_name, "")
        except Exception as e:
            logger.warning(f"[Coder] 提取模块契约失败: {e}")
            return ""

    def _normalize_module(self, module: Any, index: int):
        """标准化模块信息"""
        if isinstance(module, dict):
            module_name = module.get("name", f"module_{index}")
            module_info = module
        else:
            module_name = str(module)
            module_info = {
                "name": module_name,
                "description": f"{module_name} 模块",
                "core_features": [],
                "entities": [],
                "estimated_apis": 8,
                "module_type": "core",
                "dependencies": [],
            }
        return module_name, module_info

    def _get_preset_hint(self) -> str:
        """生成预置类提示"""
        pkg = self.project_name_safe
        lines = ["## 已由模板预置的公共类（不要重复生成）"]
        for tmpl in self.PRESET_CLASSES:
            path = tmpl.format(pkg=pkg)
            lines.append(f"- {path}")
        return "\n".join(lines)

    @retry_with_fallback(max_retries=3, delay=5, fallback_value=[])
    def _generate_phase1(self, module_name: str, module_info: Dict, system_prompt: str,
                         existing_files: List[str] = None, contract_hint: str = None,
                         module_plan_hint: str = "") -> List[Dict]:
        """Phase 1: 生成骨架代码"""
        existing_hint = ""
        if existing_files:
            existing_hint = (
                "\n\n## 已存在的文件（禁止重复生成）\n"
                + "\n".join([f"- {f}" for f in existing_files])
            )

        core_features = module_info.get("core_features", [])
        core_features_str = "、".join(core_features) if core_features else "详见模块描述"
        core_features_detail = "\n".join(f"- {f}" for f in core_features) if core_features else "- 基础功能"

        task_prompt = prompts.load(
            "coder_phase1",
            module_name=module_name,
            module_description=module_info.get("description", f"{module_name} 模块"),
            module_type=module_info.get("module_type", "core"),
            core_features=core_features_str,
            core_features_detail=core_features_detail,
            entities="、".join(module_info.get("entities", [])) if module_info.get("entities") else "待定",
            estimated_apis=module_info.get("estimated_apis", 8),
            tech_stack_detail=TECH_STACKS[self.tech_stack]["name"],
            db_schema=self.db_schema,
            api_contract=self.api_contract,
            project_name_lower=self.project_name_safe,
            contract_hint=contract_hint or "",
            existing_files_hint=existing_hint,
            module_plan=module_plan_hint or "",
        )

        logger.info(f"[Phase 1] 调用 LLM 生成 {module_name} 骨架...")
        response = self.llm.invoke([
            ("system", system_prompt),
            ("user", task_prompt)
        ])

        files = self._parse_code_output(response.content)

        # 过滤已存在文件 + 预置类
        files = self._filter_preset_duplicates(files)

        # 写入磁盘
        for f in files:
            if f["content"].strip():
                safe_write_file(self.project_dir, f["file_path"], f["content"])

        return files

    @retry_with_fallback(max_retries=3, delay=5, fallback_value=[])
    def _generate_phase2(self, module_name: str, module_info: Dict, system_prompt: str,
                         existing_files: List[str] = None, contract_hint: str = None,
                         module_plan_hint: str = "") -> List[Dict]:
        """Phase 2: 生成业务实现"""
        existing_hint = ""
        if existing_files:
            existing_hint = (
                "\n\n## 已存在的文件（禁止重复生成）\n"
                + "\n".join([f"- {f}" for f in existing_files])
            )

        core_features = module_info.get("core_features", [])
        core_features_str = "、".join(core_features) if core_features else "详见模块描述"

        task_prompt = prompts.load(
            "coder_phase2",
            module_name=module_name,
            module_description=module_info.get("description", f"{module_name} 模块"),
            module_type=module_info.get("module_type", "core"),
            core_features=core_features_str,
            entities="、".join(module_info.get("entities", [])) if module_info.get("entities") else "待定",
            estimated_apis=module_info.get("estimated_apis", 8),
            tech_stack_detail=TECH_STACKS[self.tech_stack]["name"],
            project_name_lower=self.project_name_safe,
            contract_hint=contract_hint or "",
            existing_files_hint=existing_hint,
            module_plan=module_plan_hint or "",
        )

        logger.info(f"[Phase 2] 调用 LLM 生成 {module_name} 实现...")
        response = self.llm.invoke([
            ("system", system_prompt),
            ("user", task_prompt)
        ])

        files = self._parse_code_output(response.content)

        # 过滤已存在文件 + 预置类 + Phase 1 已生成的骨架
        files = self._filter_preset_duplicates(files)
        if existing_files:
            filtered = []
            for f in files:
                if not any(f["file_path"].endswith(ex) or ex.endswith(f["file_path"]) for ex in existing_files):
                    filtered.append(f)
                else:
                    logger.info(f"[Phase 2] 过滤重复文件: {f['file_path']}")
            files = filtered

        # 写入磁盘
        for f in files:
            if f["content"].strip():
                safe_write_file(self.project_dir, f["file_path"], f["content"])

        return files

    def _filter_preset_duplicates(self, files: List[Dict]) -> List[Dict]:
        """过滤掉与预置类重复的文件"""
        pkg = self.project_name_safe
        preset_paths = set()
        for tmpl in self.PRESET_CLASSES:
            preset_paths.add(tmpl.format(pkg=pkg).replace("src/main/java/", ""))

        filtered = []
        for f in files:
            fp = f["file_path"].replace("\\", "/")
            # 检查是否是预置类的重复生成
            is_preset = any(
                fp.endswith(p.split("/")[-1]) or p in fp
                for p in preset_paths
            )
            if is_preset:
                logger.info(f"[Filter] 跳过预置类重复生成: {fp}")
                continue
            filtered.append(f)
        return filtered

    def _compile_check(self) -> Dict:
        """编译检查，返回详细结果（使用共享工具）"""
        from tools.compile_checker import compile_check
        return compile_check(self.project_dir, log_name="compile_phase1.log")

    def _extract_contracts(self, code_files: List[Dict]) -> str:
        """
        v3: 将上一阶段生成的完整代码注入 prompt，让 LLM 真正熟悉全部契约。
        不再做摘要提取，直接给出完整文件内容。
        """
        MAX_TOTAL_CHARS = 15000  # DeepSeek V4 Pro 128K 上下文，15000 字符绰绰有余

        # 优先级排序：Service 接口 > Repository > Entity > DTO > common/util
        def priority_key(f):
            path = f["file_path"]
            if "service/" in path and "service/impl/" not in path:
                return (0, path)
            if "repository/" in path:
                return (1, path)
            if "entity/" in path:
                return (2, path)
            if "dto/" in path:
                return (3, path)
            return (4, path)

        sorted_files = sorted(code_files, key=priority_key)
        sections = []
        total_len = 0

        for f in sorted_files:
            path = f["file_path"]
            fc = f["content"].strip()
            if not fc:
                continue

            # 构建文件块
            section = f"\n=== {path} ===\n{fc}\n"

            # 预算检查：Service 接口和 Repository 必须保留，其他类型超预算可跳过
            is_critical = "service/" in path or "repository/" in path
            if total_len + len(section) > MAX_TOTAL_CHARS and not is_critical:
                continue
            if total_len + len(section) > MAX_TOTAL_CHARS:
                # 连关键文件都超预算了，截断内容（保留前部 import + 类声明 + 前几个方法）
                remaining = MAX_TOTAL_CHARS - total_len - len(f"\n=== {path} ===\n") - 100
                if remaining > 500:
                    truncated = fc[:remaining]
                    # 截到最近的一个方法结束或类声明处，避免语法断裂
                    last_brace = truncated.rfind('}')
                    if last_brace > 0:
                        truncated = truncated[:last_brace + 1]
                    section = f"\n=== {path} ===\n{truncated}\n// ... (truncated for length)\n"
                else:
                    break

            sections.append(section)
            total_len += len(section)

        if not sections:
            return ""

        header = (
            "## 上一阶段已生成的完整代码（请仔细阅读并熟悉以下所有接口和类型定义）\n"
            "## 生成本阶段代码时，必须严格遵守这些契约，不得自行添加不存在的方法或字段。\n"
        )
        footer = (
            "\n【铁律】\n"
            "1. ServiceImpl 必须 implements Service 接口，并实现接口中声明的每一个方法，一个都不能漏。\n"
            "2. 只能使用以上代码中已声明的字段和方法，禁止调用不存在的 getter/setter。\n"
            "3. Controller 只能调用 Service 接口中已定义的方法，禁止自行创造新的 Service 方法。\n"
            "4. 如果接口方法需要返回 DTO/VO，请确保只设置该 DTO/VO 中已声明的字段。\n"
        )

        return header + "".join(sections) + footer

    # ==================== 以下方法基本不变 ====================

    def _post_process_java_files(self):
        """Java 代码后处理"""
        import shutil
        import re
        from tools import lombok_remover

        src_dir = os.path.join(self.project_dir, "src/main/java/com/example")
        if not os.path.exists(src_dir):
            return

        java_files = []
        original_pkgs = set()

        for root, dirs, files in os.walk(src_dir):
            for f in files:
                if f.endswith(".java"):
                    filepath = os.path.join(root, f)
                    with open(filepath, "r", encoding="utf-8") as fp:
                        content = fp.read()
                    content = content.lstrip("\ufeff")
                    for line in content.splitlines():
                        if line.strip().startswith("package "):
                            pkg = line.strip()[8:].rstrip(";").strip()
                            original_pkgs.add(pkg)
                            break
                    java_files.append((filepath, content))

        if not original_pkgs:
            return

        unified_pkg = f"com.example.{self.project_name_safe}"

        for filepath, content in java_files:
            new_content = content
            for pkg in original_pkgs:
                if pkg != unified_pkg and not pkg.startswith(unified_pkg + "."):
                    new_content = new_content.replace(f"package {pkg};", f"package {unified_pkg};")
                    new_content = new_content.replace(f"import {pkg}.", f"import {unified_pkg}.")
            with open(filepath, "w", encoding="utf-8") as fp:
                fp.write(new_content)

        demo_dir = os.path.join(src_dir, "demo")
        if os.path.exists(demo_dir):
            shutil.rmtree(demo_dir)
            logger.info("[PostProcess] 删除重复 demo 目录")

        for item in os.listdir(src_dir):
            item_path = os.path.join(src_dir, item)
            if os.path.isdir(item_path) and item != self.project_name_safe:
                target_dir = os.path.join(src_dir, self.project_name_safe)
                os.makedirs(target_dir, exist_ok=True)
                for root, dirs, files in os.walk(item_path):
                    rel = os.path.relpath(root, item_path)
                    target_subdir = os.path.join(target_dir, rel)
                    os.makedirs(target_subdir, exist_ok=True)
                    for f in files:
                        src_file = os.path.join(root, f)
                        dst_file = os.path.join(target_subdir, f)
                        if os.path.exists(dst_file):
                            os.remove(dst_file)
                        shutil.move(src_file, dst_file)
                shutil.rmtree(item_path)
                logger.info(f"[PostProcess] 重命名目录: {item} -> {self.project_name_safe}")

        lombok_remover.remove_lombok_from_project(self.project_dir)
        self._fix_packages_by_path()

        from tools import truncation_checker
        truncated = truncation_checker.check_project_for_truncation(self.project_dir)
        if truncated:
            logger.warning(f"[PostProcess] 发现 {len(truncated)} 个截断文件")
            for fp, reason in truncated:
                logger.warning(f"  - {fp}: {reason}")

        # AST 结构检查
        from tools.ast_checker import check_project
        ast_issues = check_project(self.project_dir)
        if ast_issues:
            logger.warning(f"[PostProcess] AST 检查发现 {len(ast_issues)} 个结构问题")
            for fp, line_no, desc in ast_issues[:10]:
                logger.warning(f"  - {fp}:{line_no} {desc}")
        else:
            logger.info("[PostProcess] AST 结构检查通过 ✓")

        logger.info("[PostProcess] Java 后处理完成")

    def _fix_packages_by_path(self):
        """根据文件实际路径修正 package 声明和 import"""
        import re

        base_dir = os.path.join(self.project_dir, f"src/main/java/com/example/{self.project_name_safe}")
        if not os.path.exists(base_dir):
            return

        class_map = {}
        for root, dirs, files in os.walk(base_dir):
            for f in files:
                if f.endswith(".java"):
                    class_name = f[:-5]
                    relpath = os.path.relpath(root, base_dir)
                    if relpath == ".":
                        pkg = f"com.example.{self.project_name_safe}"
                    else:
                        pkg = f"com.example.{self.project_name_safe}." + relpath.replace(os.sep, ".")
                    class_map[class_name] = pkg

        for root, dirs, files in os.walk(base_dir):
            for f in files:
                if not f.endswith(".java"):
                    continue
                filepath = os.path.join(root, f)
                with open(filepath, "r", encoding="utf-8") as fp:
                    content = fp.read()

                original = content
                relpath = os.path.relpath(root, base_dir)
                if relpath == ".":
                    correct_pkg = f"com.example.{self.project_name_safe}"
                else:
                    correct_pkg = f"com.example.{self.project_name_safe}." + relpath.replace(os.sep, ".")

                content = re.sub(r'^package\s+com\.example\.' + self.project_name_safe + r'\s*;', f'package {correct_pkg};', content, flags=re.MULTILINE)

                wildcard = f'import com.example.{self.project_name_safe}.*;'
                if wildcard in content:
                    subpackages = ['common', 'config', 'controller', 'dto', 'entity', 'exception', 'repository', 'service', 'util']
                    replacement = '\n'.join([f'import com.example.{self.project_name_safe}.{pkg}.*;' for pkg in subpackages])
                    content = content.replace(wildcard, replacement)

                def replace_import(m):
                    full = m.group(0)
                    class_name = m.group(1)
                    rest = m.group(2) or ''
                    if class_name in class_map:
                        correct_pkg = class_map[class_name]
                        return f'import {correct_pkg}.{class_name}{rest};'
                    return full

                content = re.sub(r'import\s+com\.example\.' + self.project_name_safe + r'\.([A-Z]\w*)(.*?);', replace_import, content)

                if content != original:
                    with open(filepath, "w", encoding="utf-8") as fp:
                        fp.write(content)

    def _parse_code_output(self, text: str) -> List[Dict]:
        """解析 LLM 输出，优先 JSON 数组，回退 File 标记"""
        import json

        try:
            cleaned = text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            data = json.loads(cleaned)
            if isinstance(data, list):
                files = []
                for item in data:
                    if isinstance(item, dict) and "file_path" in item and "content" in item:
                        files.append({
                            "file_path": item["file_path"],
                            "content": item["content"],
                            "language": self._detect_language(item["file_path"]),
                        })
                if files:
                    return files
        except (json.JSONDecodeError, ValueError):
            pass

        files = []
        current_file = None
        current_content = []

        for line in text.splitlines():
            file_match = None
            stripped = line.strip()
            if stripped.startswith("// File:"):
                file_match = stripped[8:].strip()
            elif stripped.startswith("# File:"):
                file_match = stripped[7:].strip()
            elif stripped.startswith("<!-- File:"):
                file_match = stripped[10:].replace("-->", "").strip()
            elif stripped.startswith("/* File:"):
                file_match = stripped[8:].replace("*/", "").strip()

            if file_match:
                if current_file and current_content:
                    files.append({
                        "file_path": current_file,
                        "content": "\n".join(current_content).strip(),
                        "language": self._detect_language(current_file),
                    })
                current_file = file_match
                current_content = []
            elif current_file is not None:
                current_content.append(line)

        if current_file and current_content:
            files.append({
                "file_path": current_file,
                "content": "\n".join(current_content).strip(),
                "language": self._detect_language(current_file),
            })

        return files

    def _detect_language(self, file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()
        mapping = {
            ".java": "java", ".py": "python", ".vue": "vue", ".js": "javascript",
            ".ts": "typescript", ".json": "json", ".xml": "xml", ".yml": "yaml",
            ".yaml": "yaml", ".sql": "sql", ".md": "markdown", ".html": "html",
        }
        return mapping.get(ext, "text")
