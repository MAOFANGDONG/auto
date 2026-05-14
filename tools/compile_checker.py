"""
共享编译检查工具
被 CoderAgent、ValidatorAgent、BuilderAgent 复用
"""
import os
import shutil
import subprocess
import sys
from typing import Dict

from loguru import logger


def compile_check(project_dir: str, log_name: str = "compile.log", timeout: int = 300) -> Dict:
    """
    编译检查，返回详细结果
    :param project_dir: 项目目录
    :param log_name: 编译日志文件名
    :param timeout: 编译超时秒数
    :return: {"success": bool, "stdout": str, "stderr": str, "error_count": int}
    """
    result = {
        "success": False,
        "stdout": "",
        "stderr": "",
        "error_count": 0,
    }
    if not os.path.exists(project_dir):
        return result

    pom_path = os.path.join(project_dir, "pom.xml")
    if not os.path.exists(pom_path):
        # Try build.gradle for future support
        gradle_path = os.path.join(project_dir, "build.gradle")
        if os.path.exists(gradle_path):
            return _gradle_compile(project_dir, log_name, timeout)
        result["stderr"] = "pom.xml 不存在"
        return result

    mvnw_cmd = os.path.join(project_dir, "mvnw.cmd" if sys.platform == "win32" else "mvnw")
    mvn_executable = mvnw_cmd if os.path.exists(mvnw_cmd) else (shutil.which("mvn") or "mvn")

    original_dir = os.getcwd()
    try:
        os.chdir(project_dir)
        cmd = f"{mvn_executable} clean compile -DskipTests -q" if sys.platform == "win32" else [mvn_executable, "clean", "compile", "-DskipTests", "-q"]
        shell = sys.platform == "win32"
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="ignore", shell=shell
        )
        result["success"] = proc.returncode == 0
        result["stdout"] = proc.stdout
        result["stderr"] = proc.stderr
        result["error_count"] = proc.stderr.count("[ERROR]") if proc.stderr else 0

        # 保存编译日志
        log_path = os.path.join(project_dir, log_name)
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"Return code: {proc.returncode}\n\nSTDOUT:\n{proc.stdout}\n\nSTDERR:\n{proc.stderr}")
    except Exception as e:
        logger.warning(f"[CompileChecker] 编译检查异常: {e}")
        result["stderr"] = str(e)
    finally:
        os.chdir(original_dir)

    return result


def _gradle_compile(project_dir: str, log_name: str, timeout: int) -> Dict:
    """Gradle 编译（预留）"""
    result = {"success": False, "stdout": "", "stderr": "", "error_count": 0}
    # TODO: implement gradle compile check
    result["stderr"] = "Gradle 编译暂不支持"
    return result
