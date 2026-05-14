"""
运行指定开题报告的全流程
"""
import os
import sys

# 必须在导入任何LangChain模块前设置
os.environ["LANGCHAIN_PYDANTIC_V2"] = "true"

from main import run_pipeline

REPORT_PATH = r"C:\Users\20160\report_text.txt"

if __name__ == "__main__":
    print("[Auto-Graduation] 读取开题报告...")
    with open(REPORT_PATH, "r", encoding="utf-8") as f:
        report_text = f.read()

    print(f"报告长度: {len(report_text)} 字符")
    print("-" * 60)
    print("启动 LangGraph 流水线...")
    print("=" * 60)

    final_state = run_pipeline(report_text, thread_id="yang_sisi_2022611434")

    print("\n" + "=" * 60)
    print(f"[FINAL] 最终阶段: {final_state['current_stage']}")
    if final_state.get('error_message'):
        print(f"[ERROR] 错误信息: {final_state['error_message']}")
    print("=" * 60)
