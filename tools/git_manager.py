"""
Git 版本控制管理器
为项目生成过程提供版本追踪、回滚和审计能力
"""
import os
import subprocess
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass
from loguru import logger


@dataclass
class GitCommit:
    """Git 提交记录"""
    hash: str
    author: str
    date: str
    message: str


class GitManager:
    """Git 管理器 - 封装所有 Git 操作"""

    # 默认 .gitignore 规则（按技术栈）
    DEFAULT_IGNORES = [
        "# Build outputs",
        "target/",
        "build/",
        "dist/",
        "*.class",
        "*.jar",
        "*.war",
        "__pycache__/",
        "*.pyc",
        "",
        "# Dependencies",
        "node_modules/",
        ".m2/",
        "venv/",
        ".venv/",
        "",
        "# IDE",
        ".idea/",
        "*.iml",
        ".vscode/",
        "*.swp",
        "",
        "# Logs",
        "*.log",
        "logs/",
        "",
        "# OS",
        ".DS_Store",
        "Thumbs.db",
        "",
        "# Auto-graduation internal",
        ".checkpoint/",
        "compile_*.log",
        "*.docx",
    ]

    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir).resolve()
        self._git_available = self._check_git_installed()
        self._repo_initialized = self._check_repo_initialized()

    # ==================== 环境检查 ====================

    def _check_git_installed(self) -> bool:
        """检查系统是否安装了 git"""
        try:
            result = subprocess.run(
                ["git", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                logger.debug(f"[Git] {result.stdout.strip()}")
                return True
        except Exception:
            pass
        logger.warning("[Git] 系统未安装 git，Git 功能将不可用")
        return False

    def _check_repo_initialized(self) -> bool:
        """检查是否已初始化 git 仓库"""
        git_dir = self.project_dir / ".git"
        return git_dir.exists() and git_dir.is_dir()

    @property
    def available(self) -> bool:
        """Git 功能是否可用"""
        return self._git_available

    @property
    def initialized(self) -> bool:
        """仓库是否已初始化"""
        return self._repo_initialized

    # ==================== 核心操作 ====================

    def init_repo(self, tech_stack: str = "java", extra_patterns: List[str] = None) -> bool:
        """
        初始化 Git 仓库并创建初始提交
        :param tech_stack: 技术栈，用于生成针对性的 .gitignore
        :param extra_patterns: .gitignore 的额外规则
        """
        if not self.available:
            return False

        if self.initialized:
            logger.info(f"[Git] 仓库已存在: {self.project_dir}")
            return True

        try:
            # 配置 git 用户信息（局部，不影响全局）
            self._run_git(["init"])
            self._run_git(["config", "user.name", "AutoGraduation-Agent"])
            self._run_git(["config", "user.email", "agent@auto-graduation.dev"])

            self._create_gitignore(tech_stack, extra_patterns or [])

            # 初始提交（模板文件）
            self._run_git(["add", "."])
            self._run_git([
                "commit", "-m",
                "[init] 初始化项目模板\n\n技术栈: {}".format(tech_stack),
            ])
            self._repo_initialized = True

            commit_hash = self.get_current_commit()
            logger.info(f"[Git] 仓库初始化完成，初始提交: {commit_hash[:8] if commit_hash else 'unknown'}")
            return True
        except Exception as e:
            logger.error(f"[Git] 初始化失败: {e}")
            return False

    def commit(self, message: str, stage: str = "", details: dict = None) -> Optional[str]:
        """
        提交当前所有修改
        :param message: 提交信息主体
        :param stage: 阶段标记，如 architect/coder/validator/fix/build
        :param details: 额外信息字典，会格式化为提交信息的尾部
        :return: commit hash，失败返回 None
        """
        if not self.available or not self.initialized:
            return None

        # 检查是否有变更需要提交
        status = self._run_git(["status", "--porcelain"], check=False)
        if not status.stdout.strip():
            logger.debug(f"[Git] 无变更，跳过提交: {message[:50]}")
            return self.get_current_commit()

        # 构建规范化的提交信息
        prefix = f"[{stage}]" if stage else "[auto]"
        full_message = f"{prefix} {message}"

        if details:
            full_message += "\n\n"
            for k, v in details.items():
                full_message += f"{k}: {v}\n"

        try:
            self._run_git(["add", "-A"])
            self._run_git(["commit", "-m", full_message])
            commit_hash = self.get_current_commit()
            logger.info(f"[Git] 已提交: {commit_hash[:8]} - {full_message.split(chr(10))[0][:60]}")
            return commit_hash
        except Exception as e:
            logger.error(f"[Git] 提交失败: {e}")
            return None

    def get_current_commit(self) -> Optional[str]:
        """获取当前 HEAD 的 commit hash"""
        if not self.available or not self.initialized:
            return None

        result = self._run_git(["rev-parse", "HEAD"], check=False)
        if result.returncode == 0:
            return result.stdout.strip()
        return None

    def get_log(self, n: int = 20) -> List[GitCommit]:
        """获取提交历史"""
        if not self.available or not self.initialized:
            return []

        result = self._run_git([
            "log", f"-{n}",
            "--pretty=format:%H|%an|%ad|%s",
            "--date=short"
        ], check=False)

        commits = []
        for line in result.stdout.strip().split("\n"):
            if "|" in line:
                parts = line.split("|", 3)
                if len(parts) == 4:
                    commits.append(GitCommit(*parts))
        return commits

    def get_diff(self, commit1: str = None, commit2: str = None) -> str:
        """
        获取差异
        :param commit1: 起始 commit（默认 HEAD~1）
        :param commit2: 结束 commit（默认 HEAD）
        """
        if not self.available or not self.initialized:
            return ""

        if commit1 and commit2:
            result = self._run_git(["diff", commit1, commit2], check=False)
        elif commit1:
            result = self._run_git(["diff", commit1], check=False)
        else:
            result = self._run_git(["diff", "HEAD~1", "HEAD"], check=False)

        return result.stdout

    def get_diff_stat(self, commit1: str = None, commit2: str = None) -> str:
        """获取差异统计（文件数、行数）"""
        if not self.available or not self.initialized:
            return ""

        args = ["diff", "--stat"]
        if commit1 and commit2:
            args.extend([commit1, commit2])
        elif commit1:
            args.append(commit1)
        else:
            args.extend(["HEAD~1", "HEAD"])

        result = self._run_git(args, check=False)
        return result.stdout

    def reset_hard(self, commit: str = "HEAD") -> bool:
        """
        硬回滚到指定 commit
        :param commit: commit hash 或 HEAD/HEAD~1 等
        :return: 是否成功
        """
        if not self.available or not self.initialized:
            return False

        try:
            self._run_git(["reset", "--hard", commit])
            logger.info(f"[Git] 已回滚到: {commit}")
            return True
        except Exception as e:
            logger.error(f"[Git] 回滚失败: {e}")
            return False

    def stash(self, message: str = "") -> bool:
        """暂存当前修改（包含 untracked 文件）"""
        if not self.available or not self.initialized:
            return False

        try:
            cmd = ["stash", "push", "-u", "-k"]  # -u 包含 untracked, -k 保留 staged
            if message:
                cmd.extend(["-m", message])
            self._run_git(cmd)
            logger.info(f"[Git] 已暂存修改: {message[:50] if message else '(无说明)'}")
            return True
        except Exception as e:
            logger.error(f"[Git] 暂存失败: {e}")
            return False

    def stash_pop(self) -> bool:
        """恢复暂存"""
        if not self.available or not self.initialized:
            return False

        try:
            # 先检查是否有 stash
            result = self._run_git(["stash", "list"], check=False)
            if not result.stdout.strip():
                logger.debug("[Git] 没有可恢复的暂存")
                return True

            self._run_git(["stash", "pop"])
            logger.info("[Git] 已恢复暂存")
            return True
        except Exception as e:
            logger.error(f"[Git] 恢复暂存失败: {e}")
            return False

    def get_changed_files(self, commit1: str = None, commit2: str = None) -> List[str]:
        """获取变更的文件列表（相对路径）"""
        if not self.available or not self.initialized:
            return []

        args = ["diff", "--name-only"]
        if commit1 and commit2:
            args.extend([commit1, commit2])
        elif commit1:
            args.append(commit1)
        else:
            args.extend(["HEAD~1", "HEAD"])

        result = self._run_git(args, check=False)
        return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]

    def create_tag(self, tag_name: str, message: str = "") -> bool:
        """创建标签（用于标记里程碑，如编译通过）"""
        if not self.available or not self.initialized:
            return False

        try:
            cmd = ["tag", "-a", tag_name, "-m", message or f"Milestone: {tag_name}"]
            self._run_git(cmd)
            logger.info(f"[Git] 已创建标签: {tag_name}")
            return True
        except Exception as e:
            logger.error(f"[Git] 创建标签失败: {e}")
            return False

    def get_branch_name(self) -> Optional[str]:
        """获取当前分支名"""
        if not self.available or not self.initialized:
            return None

        result = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"], check=False)
        if result.returncode == 0:
            return result.stdout.strip()
        return None

    def status_summary(self) -> dict:
        """获取当前工作区状态摘要"""
        if not self.available or not self.initialized:
            return {"available": False}

        result = {
            "available": True,
            "initialized": True,
            "branch": self.get_branch_name(),
            "commit": self.get_current_commit(),
            "commit_count": 0,
            "latest_commit": None,
        }

        log = self.get_log(n=1)
        if log:
            result["latest_commit"] = log[0].message
            result["commit_count"] = len(self.get_log(n=999))

        return result

    # ==================== 内部方法 ====================

    def _run_git(self, args: List[str], check: bool = True) -> subprocess.CompletedProcess:
        """运行 git 命令"""
        cmd = ["git"] + args
        logger.debug(f"[Git] 执行: {' '.join(cmd)} (cwd: {self.project_dir})")

        # Windows 兼容：确保目录存在
        os.makedirs(self.project_dir, exist_ok=True)

        result = subprocess.run(
            cmd,
            cwd=str(self.project_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )

        if check and result.returncode != 0:
            stderr = result.stderr.strip()
            raise RuntimeError(f"Git 命令失败: git {' '.join(args)}\n{stderr}")

        return result

    def _create_gitignore(self, tech_stack: str, extra_patterns: List[str]):
        """创建 .gitignore 文件"""
        lines = list(self.DEFAULT_IGNORES)

        # 技术栈特定规则
        if tech_stack == "java":
            lines.extend([
                "",
                "# Java / Maven",
                ".gradle/",
            ])
        elif tech_stack == "python":
            lines.extend([
                "",
                "# Python",
                "*.egg-info/",
                ".pytest_cache/",
            ])

        if extra_patterns:
            lines.extend(["", "# Custom"] + extra_patterns)

        gitignore_path = self.project_dir / ".gitignore"
        gitignore_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"[Git] 创建 .gitignore")


# ==================== 便捷函数 ====================

def get_git_manager(project_dir: str) -> GitManager:
    """获取 GitManager 实例"""
    return GitManager(project_dir)


def commit_on_stage(project_dir: str, stage: str, message: str, details: dict = None) -> Optional[str]:
    """
    便捷函数：在指定阶段提交变更
    :return: commit hash 或 None
    """
    gm = GitManager(project_dir)
    if not gm.initialized:
        logger.warning(f"[Git] 项目未初始化 Git 仓库，跳过提交: {message[:50]}")
        return None
    return gm.commit(message=message, stage=stage, details=details)
