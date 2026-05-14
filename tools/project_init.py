"""
项目初始化工具
从模板目录复制预置骨架到 workspace
"""
import os
import re
import shutil
from pathlib import Path
from jinja2 import Template
from loguru import logger

from config import TEMPLATES_DIR, TECH_STACKS
from tools.git_manager import GitManager


def _to_safe_name(name: str) -> str:
    """把项目名称转为安全的英文标识符（artifactId / 包名）"""
    # 先去掉所有非 ASCII 字符
    ascii_only = re.sub(r'[^\x00-\x7F]', '', name)
    safe = ascii_only.lower().strip().replace(" ", "_")
    safe = re.sub(r'[^a-z0-9_-]', '', safe)
    # 不能以数字开头
    if safe and safe[0].isdigit():
        safe = "p_" + safe
    return safe or "project"


def init_project_from_template(tech_stack: str, project_name: str, output_dir: str) -> str:
    """
    根据技术栈初始化项目目录
    :param tech_stack: "java" 或 "python"
    :param project_name: 项目名称（可能是中文）
    :param output_dir: 输出目录（绝对路径）
    :return: 项目目录路径
    """
    template_dir = Path(TEMPLATES_DIR) / TECH_STACKS[tech_stack]["template_dir"]
    project_dir = Path(output_dir)

    if not template_dir.exists():
        raise FileNotFoundError(f"模板目录不存在: {template_dir}")

    # 清空或创建项目目录
    if project_dir.exists():
        shutil.rmtree(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)

    # 生成安全名称（用于 pom.xml artifactId、包名等）
    project_name_safe = _to_safe_name(project_name)

    # 复制模板文件（包括隐藏文件如 .mvn）
    all_files = list(template_dir.rglob("*")) + list(template_dir.rglob(".*"))
    # 去重
    seen = set()
    for src_path in all_files:
        if src_path in seen:
            continue
        seen.add(src_path)
        if src_path.is_file():
            rel_path = src_path.relative_to(template_dir)
            # 路径中的 demo 替换为安全项目名
            rel_path_str = str(rel_path).replace("/demo/", f"/{project_name_safe}/").replace("\\demo\\", f"\\{project_name_safe}\\")
            # 如果文件名本身就是 demo 相关（如 Application.java 在 demo 目录下）
            if str(rel_path).startswith("demo/") or str(rel_path).startswith("demo\\"):
                rel_path_str = str(rel_path).replace("demo/", f"{project_name_safe}/", 1).replace("demo\\", f"{project_name_safe}\\", 1)
            rel_path = Path(rel_path_str)
            dst_path = project_dir / rel_path
            dst_path.parent.mkdir(parents=True, exist_ok=True)

            # 判断是否为文本文件（可渲染 Jinja2）
            text_extensions = {
                '.java', '.xml', '.properties', '.yml', '.yaml', '.txt', '.md',
                '.sql', '.json', '.html', '.css', '.js', '.vue', '.ts', '.gradle',
                '.gitignore', '.gitattributes',
            }
            if src_path.suffix.lower() in text_extensions or src_path.name.lower() in text_extensions:
                content = src_path.read_text(encoding="utf-8")
                rendered = Template(content).render(
                    project_name=project_name,
                    project_name_lower=project_name_safe,
                    project_name_safe=project_name_safe,
                )
                dst_path.write_text(rendered, encoding="utf-8")
            else:
                shutil.copy2(str(src_path), str(dst_path))

    # 初始化 Git 仓库
    git = GitManager(str(project_dir))
    git.init_repo(tech_stack=tech_stack)

    logger.info(f"项目初始化完成: {project_dir}")
    return str(project_dir)


def get_template_structure(tech_stack: str) -> dict:
    """获取模板的目录结构（用于 Architect Agent 参考）"""
    template_dir = Path(TEMPLATES_DIR) / TECH_STACKS[tech_stack]["template_dir"]
    if not template_dir.exists():
        return {}

    structure = {"files": [], "dirs": []}
    for path in template_dir.rglob("*"):
        rel = str(path.relative_to(template_dir))
        if path.is_file():
            structure["files"].append(rel)
        else:
            structure["dirs"].append(rel)
    return structure
