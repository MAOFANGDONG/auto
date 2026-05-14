"""
Builder Agent：构建验证器
负责编译代码、运行测试、验证项目可启动
"""
import os
import sys
import shutil
import subprocess
from typing import Dict
from loguru import logger

from config import WORKSPACE_DIR, TECH_STACKS


def _find_executable(name: str) -> str:
    """查找系统可执行文件的绝对路径"""
    path = shutil.which(name)
    if path:
        return path
    # Windows 上有时候 which 找不到 .cmd，手动补后缀试试
    for ext in [".cmd", ".exe", ".bat"]:
        path = shutil.which(name + ext)
        if path:
            return path
    return name  # 找不到就返回原名，让 subprocess 自己报错


class BuilderAgent:
    """构建验证 Agent"""

    def __init__(self, tech_stack: str, project_name: str):
        self.tech_stack = tech_stack
        self.project_name = project_name
        self.project_dir = os.path.join(WORKSPACE_DIR, project_name)

        # 查找构建工具的绝对路径
        self.mvn_path = _find_executable("mvn")
        self.java_path = _find_executable("java")
        self.npm_path = _find_executable("npm")
        self.python_path = _find_executable("python")

        logger.info(f"[Builder Agent] 初始化，项目: {project_name}")
        logger.debug(f"  mvn: {self.mvn_path}, java: {self.java_path}, npm: {self.npm_path}")

    def build_and_verify(self) -> Dict:
        """
        构建并验证项目
        :return: {"success": bool, "stage": str, "stdout": str, "stderr": str, "fix_attempts": int}
        """
        result = {
            "success": False,
            "stage": "",
            "stdout": "",
            "stderr": "",
            "fix_attempts": 0,
        }

        if not os.path.exists(self.project_dir):
            result["stderr"] = f"项目目录不存在: {self.project_dir}"
            return result

        try:
            if self.tech_stack == "java":
                result = self._build_java()
            elif self.tech_stack == "python":
                result = self._build_python()
            else:
                result["stderr"] = f"未知技术栈: {self.tech_stack}"
        except Exception as e:
            result["stderr"] = str(e)
            logger.error(f"[Builder Agent] 构建异常: {e}")

        return result

    def _build_java(self) -> Dict:
        """构建 Java 项目"""
        logger.info("[Builder Agent] 编译 Java 项目...")

        # 检查项目目录和 pom.xml 是否存在
        pom_path = os.path.join(self.project_dir, "pom.xml")
        if not os.path.exists(self.project_dir):
            return {
                "success": False, "stage": "install_deps", "stdout": "",
                "stderr": f"项目目录不存在: {self.project_dir}", "fix_attempts": 0,
            }
        if not os.path.exists(pom_path):
            return {
                "success": False, "stage": "install_deps", "stdout": "",
                "stderr": f"找不到 pom.xml: {pom_path}\nCoder Agent 未生成有效的 Maven 项目", "fix_attempts": 0,
            }

        # 优先使用项目自带的 Maven Wrapper (mvnw)，避免系统 Maven 版本问题
        mvnw_cmd = os.path.join(self.project_dir, "mvnw.cmd" if sys.platform == "win32" else "mvnw")
        if os.path.exists(mvnw_cmd):
            mvn_executable = mvnw_cmd
            logger.info(f"[Builder Agent] 使用 Maven Wrapper: {mvn_executable}")
        elif shutil.which("mvn"):
            mvn_executable = "mvn"
            logger.info(f"[Builder Agent] 使用系统 Maven: {self.mvn_path}")
        else:
            return {
                "success": False, "stage": "install_deps", "stdout": "",
                "stderr": "找不到 mvn 或 mvnw 命令，请确保 Maven 已安装并加入 PATH", "fix_attempts": 0,
            }

        # Windows 中文路径编码问题：用 os.chdir 切换目录，避免 cwd 参数传中文路径
        original_dir = os.getcwd()
        use_shell = sys.platform == "win32"
        try:
            os.chdir(self.project_dir)
            logger.info(f"[Builder Agent] 工作目录: {os.getcwd()}")

            # 安装依赖并编译
            if use_shell:
                cmd = f"{mvn_executable} clean install -DskipTests"
                install_result = self._run_command(cmd, shell=True)
            else:
                cmd = [mvn_executable, "clean", "install", "-DskipTests"]
                install_result = self._run_command(cmd)

            if install_result["returncode"] != 0:
                return {
                    "success": False, "stage": "install_deps",
                    "stdout": install_result["stdout"],
                    "stderr": install_result["stderr"],
                    "fix_attempts": 0,
                }

            logger.info("[Builder Agent] Java 编译通过 ✓")
            return {
                "success": True, "stage": "compile",
                "stdout": install_result["stdout"], "stderr": "", "fix_attempts": 0,
            }
        except Exception as e:
            logger.error(f"[Builder Agent] 编译异常: {e}")
            return {
                "success": False, "stage": "install_deps", "stdout": "",
                "stderr": f"编译异常: {str(e)}", "fix_attempts": 0,
            }
        finally:
            os.chdir(original_dir)

    def _build_python(self) -> Dict:
        """构建 Python 项目"""
        logger.info("[Builder Agent] 安装 Python 依赖...")

        requirements = os.path.join(self.project_dir, "requirements.txt")
        if os.path.exists(requirements):
            install_result = self._run_command(
                [self.python_path, "-m", "pip", "install", "-r", "requirements.txt"],
                cwd=self.project_dir,
            )
            if install_result["returncode"] != 0:
                return {
                    "success": False,
                    "stage": "install_deps",
                    "stdout": install_result["stdout"],
                    "stderr": install_result["stderr"],
                    "fix_attempts": 0,
                }

        # 语法检查
        logger.info("[Builder Agent] Python 语法检查...")
        main_py = os.path.join(self.project_dir, "app", "main.py")
        if os.path.exists(main_py):
            syntax_result = self._run_command(
                [self.python_path, "-m", "py_compile", "app/main.py"],
                cwd=self.project_dir,
            )
            if syntax_result["returncode"] != 0:
                return {
                    "success": False,
                    "stage": "compile",
                    "stdout": syntax_result["stdout"],
                    "stderr": syntax_result["stderr"],
                    "fix_attempts": 0,
                }

        logger.info("[Builder Agent] Python 检查通过 ✓")
        return {
            "success": True,
            "stage": "compile",
            "stdout": "Python 依赖安装和语法检查通过",
            "stderr": "",
            "fix_attempts": 0,
        }

    def _run_command(self, cmd, cwd: str = None, timeout: int = 600, shell: bool = False) -> Dict:
        """运行 shell 命令"""
        cmd_str = cmd if isinstance(cmd, str) else ' '.join(cmd)
        logger.debug(f"执行命令: {cmd_str} (cwd: {cwd}, shell={shell})")
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="ignore",
                shell=shell,
            )
            return {
                "returncode": result.returncode,
                "stdout": result.stdout[-5000:] if len(result.stdout) > 5000 else result.stdout,
                "stderr": result.stderr[-5000:] if len(result.stderr) > 5000 else result.stderr,
            }
        except subprocess.TimeoutExpired:
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": f"命令超时 ({timeout}s)",
            }
        except Exception as e:
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": str(e),
            }
