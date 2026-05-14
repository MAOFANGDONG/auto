"""
安全文件写入工具
防止 Agent 写出项目目录外的文件，自动创建父目录
"""
import os
from pathlib import Path
from loguru import logger


def safe_write_file(base_dir: str, relative_path: str, content: str, encoding: str = "utf-8") -> str:
    """
    安全写入文件
    :param base_dir: 项目基础目录（绝对路径）
    :param relative_path: 文件相对路径，如 src/main/java/User.java
    :param content: 文件内容
    :param encoding: 编码
    :return: 写入的绝对路径
    """
    # 解析路径
    base = Path(base_dir).resolve()
    target = (base / relative_path).resolve()

    # 安全检查：确保文件在 base_dir 内
    try:
        target.relative_to(base)
    except ValueError:
        raise ValueError(f"非法路径: {relative_path} 试图写入项目目录外")

    # 自动创建父目录
    target.parent.mkdir(parents=True, exist_ok=True)

    # 写入文件（确保无 BOM）
    import codecs
    # 防御：去除内容开头的 BOM 字符
    if content.startswith('\ufeff'):
        content = content[1:]
    with codecs.open(str(target), 'w', encoding=encoding) as f:
        f.write(content)
    logger.info(f"写入文件: {target}")

    return str(target)


def safe_read_file(base_dir: str, relative_path: str, encoding: str = "utf-8") -> str:
    """安全读取文件"""
    base = Path(base_dir).resolve()
    target = (base / relative_path).resolve()

    try:
        target.relative_to(base)
    except ValueError:
        raise ValueError(f"非法路径: {relative_path}")

    if not target.exists():
        raise FileNotFoundError(f"文件不存在: {target}")

    return target.read_text(encoding=encoding)


def list_files(base_dir: str, pattern: str = "**/*") -> list:
    """列出目录下所有文件（相对路径）"""
    base = Path(base_dir).resolve()
    return [str(p.relative_to(base)) for p in base.glob(pattern) if p.is_file()]
