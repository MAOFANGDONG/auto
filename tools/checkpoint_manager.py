"""
断点恢复管理器
保存/加载项目生成过程中的状态快照，支持中断后继续
"""
import json
import os
from pathlib import Path
from loguru import logger

from config import WORKSPACE_DIR


class CheckpointManager:
    """项目生成断点管理器"""

    def __init__(self, project_name: str):
        self.project_dir = os.path.join(WORKSPACE_DIR, project_name)
        self.checkpoint_dir = os.path.join(self.project_dir, ".checkpoint")
        self.state_file = os.path.join(self.checkpoint_dir, "state.json")
        os.makedirs(self.checkpoint_dir, exist_ok=True)

    def save(self, state: dict):
        """保存状态快照（排除超大字段）"""
        # 排除 report_text（太大，从文件路径恢复）
        # 排除 code_files 的 content（已写入磁盘）
        snapshot = {}
        for key, value in state.items():
            if key == "report_text":
                snapshot[key] = value[:500] + "...[truncated]" if len(value) > 500 else value
            elif key == "code_files":
                # 只保存文件路径列表，不保存内容
                snapshot[key] = [{"file_path": f.get("file_path", ""), "language": f.get("language", "")} for f in value]
            elif key == "db_schema":
                snapshot[key] = value[:2000] + "...[truncated]" if len(value) > 2000 else value
            elif key == "api_contract":
                snapshot[key] = value[:2000] + "...[truncated]" if len(value) > 2000 else value
            elif key == "requirements_summary":
                snapshot[key] = value[:2000] + "...[truncated]" if len(value) > 2000 else value
            elif key == "logs":
                # 日志只保留最近 50 条
                snapshot[key] = value[-50:] if len(value) > 50 else value
            else:
                snapshot[key] = value

        try:
            # 保存当前 git commit hash（用于恢复时定位）
            try:
                from tools.git_manager import GitManager
                gm = GitManager(self.project_dir)
                if gm.initialized:
                    snapshot["last_git_commit"] = gm.get_current_commit()
            except Exception:
                pass

            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)

            logger.info(f"[Checkpoint] 已保存: {state.get('current_stage', 'unknown')}")
        except Exception as e:
            logger.warning(f"[Checkpoint] 保存失败: {e}")

    def load(self) -> dict:
        """加载状态快照"""
        if not os.path.exists(self.state_file):
            return None
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
            logger.info(f"[Checkpoint] 已恢复: {state.get('current_stage', 'unknown')}")
            return state
        except Exception as e:
            logger.warning(f"[Checkpoint] 加载失败: {e}")
            return None

    def clear(self):
        """清除断点"""
        if os.path.exists(self.state_file):
            os.remove(self.state_file)
            logger.info("[Checkpoint] 已清除")

    def exists(self) -> bool:
        """检查是否存在断点"""
        return os.path.exists(self.state_file)
