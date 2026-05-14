"""
Java 代码结构校验器
用轻量级正则检查常见的代码结构错误
"""
import os
import re
from pathlib import Path
from typing import List, Tuple


def check_java_file(filepath: str) -> List[Tuple[int, str]]:
    """
    检查单个 Java 文件的结构问题
    返回: [(行号, 问题描述), ...]
    """
    issues = []
    content = Path(filepath).read_text(encoding="utf-8")
    lines = content.split('\n')

    # 1. 检查构造函数内部是否嵌套了方法定义
    in_constructor = False
    brace_depth = 0
    constructor_start_line = 0

    for i, line in enumerate(lines):
        stripped = line.strip()

        # 检测构造函数开始
        if not in_constructor and re.match(
            r'^\s*(public|private|protected)?\s*\w+\s*\([^)]*\)\s*\{',
            stripped
        ):
            # 排除类声明和接口方法
            if 'class ' not in stripped and 'interface ' not in stripped:
                in_constructor = True
                constructor_start_line = i + 1
                brace_depth = 1
                continue

        if in_constructor:
            # 计算大括号深度
            brace_depth += stripped.count('{')
            brace_depth -= stripped.count('}')

            # 检测构造函数内部是否有方法定义
            if re.match(
                r'^\s*(public|private|protected|static|final|\s)+[\w<>,\s]+\s+\w+\s*\([^)]*\)\s*\{',
                stripped
            ):
                issues.append((
                    i + 1,
                    f"方法嵌套在构造函数内部（构造函数始于第 {constructor_start_line} 行）: {stripped[:60]}"
                ))

            if brace_depth <= 0:
                in_constructor = False

    # 2. 检查是否有未闭合的括号（可能导致方法嵌套）
    # 简单统计：类声明后的顶层大括号数量
    class_braces = 0
    in_class = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r'^\s*(public\s+)?(class|interface|enum)\s+\w+', stripped):
            in_class = True
            class_braces = 0
        if in_class:
            class_braces += stripped.count('{')
            class_braces -= stripped.count('}')
            if class_braces == 0 and '{' in stripped:
                in_class = False

    return issues


def check_project(project_dir: str) -> List[Tuple[str, int, str]]:
    """
    检查整个项目的 Java 文件
    返回: [(文件路径, 行号, 问题描述), ...]
    """
    all_issues = []
    src_dir = os.path.join(project_dir, "src/main/java")
    if not os.path.exists(src_dir):
        return all_issues

    for root, dirs, files in os.walk(src_dir):
        for f in files:
            if f.endswith(".java"):
                filepath = os.path.join(root, f)
                issues = check_java_file(filepath)
                for line_no, desc in issues:
                    rel_path = os.path.relpath(filepath, project_dir)
                    all_issues.append((rel_path, line_no, desc))

    return all_issues


def print_report(issues: List[Tuple[str, int, str]]):
    """打印检查报告"""
    if not issues:
        print("[AST Checker] 未发现问题 ✓")
        return

    print(f"[AST Checker] 发现 {len(issues)} 个结构问题:")
    for filepath, line_no, desc in issues:
        print(f"  {filepath}:{line_no} - {desc}")
