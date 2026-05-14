"""
Prompt 加载器
支持 Jinja2 模板渲染 + 文件热加载
修改 prompts/ 下的 .txt 文件后无需重启程序
"""
import os
import time
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

PROMPTS_DIR = Path(__file__).parent


class PromptLoader:
    """Prompt 热加载器"""

    def __init__(self):
        self._cache: dict = {}
        self._mtime_cache: dict = {}
        self._jinja = Environment(
            loader=FileSystemLoader(str(PROMPTS_DIR)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def load(self, name: str, **variables) -> str:
        """
        加载 Prompt 模板
        :param name: 文件名（不含 .txt 后缀）
        :param variables: Jinja2 模板变量
        :return: 渲染后的字符串
        """
        filepath = PROMPTS_DIR / f"{name}.txt"

        if not filepath.exists():
            raise FileNotFoundError(f"Prompt 文件不存在: {filepath}")

        # 检查文件是否被修改
        current_mtime = filepath.stat().st_mtime
        cache_key = f"{name}_{current_mtime}"

        if cache_key not in self._cache:
            raw = filepath.read_text(encoding="utf-8")
            self._cache[cache_key] = raw
            self._mtime_cache[name] = current_mtime

        template = self._jinja.from_string(self._cache[cache_key])
        return template.render(**variables)

    def load_raw(self, name: str) -> str:
        """加载纯文本，不做 Jinja2 渲染"""
        filepath = PROMPTS_DIR / f"{name}.txt"
        if not filepath.exists():
            raise FileNotFoundError(f"Prompt 文件不存在: {filepath}")
        return filepath.read_text(encoding="utf-8")


# 全局单例
prompts = PromptLoader()
