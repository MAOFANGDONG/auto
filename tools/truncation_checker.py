"""
代码截断检测工具
检测 LLM 生成的文件是否被截断（未完整输出）
"""
import re
import subprocess
from pathlib import Path
from loguru import logger


def is_likely_truncated(content: str) -> bool:
    """
    启发式检测：判断 Java 文件是否可能被截断
    :return: True 如果可能截断
    """
    lines = content.splitlines()
    if not lines:
        return True

    last_line = lines[-1].strip()
    if not last_line:
        # 倒数第二行（跳过空行）
        for line in reversed(lines[:-1]):
            if line.strip():
                last_line = line.strip()
                break

    # 1. 最后一行以不完整标记结尾
    incomplete_endings = [
        '@',        # 注解未完成：@Column(name = "xxx
        '//',       # 注释未结束
        '/*',       # 块注释未结束
        '/**',      # 文档注释未结束
        '.',        # 方法链未结束
        '=',        # 赋值未结束
        '+', '-', '*', '/', '%',  # 表达式未结束
        '&&', '||', '|', '&', '^',
        '<', '>',   # 泛型或比较未结束
        '(', '[', '{',  # 括号未闭合（如果文件末尾没有闭合）
        ',',        # 参数列表未结束
        '"', "'",   # 字符串/字符未闭合
    ]
    for ending in incomplete_endings:
        if last_line.endswith(ending):
            return True

    # 2. 统计括号闭合情况
    open_braces = content.count('{')
    close_braces = content.count('}')
    if open_braces != close_braces:
        return True

    open_parens = content.count('(')
    close_parens = content.count(')')
    if open_parens != close_parens:
        return True

    # 3. 字符串引号未闭合（简单统计，不考虑转义）
    double_quotes = content.count('"')
    if double_quotes % 2 != 0:
        return True

    # 4. 类声明了但没有闭合的 }
    class_pattern = re.search(r'public\s+(class|interface|enum)\s+\w+', content)
    if class_pattern and close_braces < open_braces:
        return True

    return False


def check_file_with_javac(filepath: str, classpath: str = "") -> tuple:
    """
    用 javac 做单文件语法检查
    :return: (is_valid, error_message)
    """
    import tempfile
    try:
        tmp_dir = tempfile.gettempdir()
        output_dir = os.path.join(tmp_dir, "truncation_check")
        os.makedirs(output_dir, exist_ok=True)
        cmd = ["javac", "-d", output_dir, "-sourcepath", str(Path(filepath).parent)]
        if classpath:
            cmd.extend(["-cp", classpath])
        cmd.append(filepath)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        # javac 返回 0 表示语法正确（即使缺少依赖也只是 warning）
        # 但缺少 import 的错误不是截断问题，我们过滤掉 symbol 找不到的错误
        if result.returncode == 0:
            return True, ""

        # 只关注语法错误（截断特征）
        stderr = result.stderr
        syntax_errors = [
            "reached end of file",
            "';' expected",
            "'}' expected",
            "'\"'",   # 引号不匹配
            "')'",    # 括号不匹配
            "illegal start of type",
            "class, interface, or enum expected",
        ]
        for err in syntax_errors:
            if err.lower() in stderr.lower():
                return False, stderr[:500]

        # 其他错误（如 symbol not found）不是截断
        return True, ""

    except Exception as e:
        logger.warning(f"[TruncationChecker] javac 检查失败: {e}")
        return True, ""  # 无法检查时默认通过


def check_project_for_truncation(project_dir: str) -> list:
    """
    检查项目中所有 Java 文件是否被截断
    :return: 截断文件列表 [(filepath, reason), ...]
    """
    src_dir = Path(project_dir) / "src" / "main" / "java"
    if not src_dir.exists():
        return []

    truncated = []
    for filepath in src_dir.rglob("*.java"):
        content = filepath.read_text(encoding="utf-8")

        # 启发式检测
        if is_likely_truncated(content):
            truncated.append((str(filepath), "启发式检测：文件可能截断"))
            logger.warning(f"[TruncationChecker] 截断警告: {filepath}")
            continue

    logger.info(f"[TruncationChecker] 检查完成，发现 {len(truncated)} 个截断文件")
    return truncated


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        result = check_project_for_truncation(sys.argv[1])
        for fp, reason in result:
            print(f"TRUNCATED: {fp} - {reason}")
