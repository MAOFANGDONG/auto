"""
Coder Agent 断点续跑脚本
从已有代码提取契约，继续生成剩余模块
"""
import os
import json

os.environ["LANGCHAIN_PYDANTIC_V2"] = "true"

from agents.coder_agent import CoderAgent
from config import WORKSPACE_DIR, TECH_STACKS
from prompts.prompt_loader import prompts

PROJECT_NAME = "child_mental_health_management_system"
PROJECT_DIR = os.path.join(WORKSPACE_DIR, PROJECT_NAME)

# 根据已有实体构造 schema（避免再调一次 Architect Agent）
DB_SCHEMA = """
CREATE TABLE users (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    nickname VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE notifications (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    title VARCHAR(200) NOT NULL,
    content TEXT,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE health_knowledge (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL,
    content TEXT,
    category VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE assessments (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    type VARCHAR(50),
    duration INT,
    total_score INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE questions (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    assessment_id BIGINT NOT NULL,
    question_text TEXT NOT NULL,
    option_a VARCHAR(255),
    option_b VARCHAR(255),
    option_c VARCHAR(255),
    option_d VARCHAR(255),
    correct_answer VARCHAR(10),
    score INT DEFAULT 0,
    sort_order INT DEFAULT 0
);

CREATE TABLE user_assessments (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    assessment_id BIGINT NOT NULL,
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP,
    score INT DEFAULT 0,
    status VARCHAR(20) DEFAULT 'IN_PROGRESS'
);

CREATE TABLE user_answers (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_assessment_id BIGINT NOT NULL,
    question_id BIGINT NOT NULL,
    user_answer VARCHAR(255),
    is_correct BOOLEAN
);

CREATE TABLE consultations (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    appointment_time TIMESTAMP,
    status VARCHAR(20) DEFAULT 'PENDING',
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE psychologists (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL UNIQUE,
    name VARCHAR(50),
    title VARCHAR(100),
    expertise VARCHAR(255),
    available_time VARCHAR(255),
    status VARCHAR(20) DEFAULT 'ACTIVE',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE banners (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    title VARCHAR(200),
    image_url VARCHAR(500),
    link_url VARCHAR(500),
    sort_order INT DEFAULT 0,
    status VARCHAR(20) DEFAULT 'ENABLED',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

API_CONTRACT = """
openapi: 3.0.0
info:
  title: Child Mental Health Management System API
  version: 1.0.0
paths:
  /api/auth/register:
    post: { summary: 用户注册 }
  /api/auth/login:
    post: { summary: 用户登录 }
  /api/user/me:
    get: { summary: 获取当前用户信息 }
  /api/notifications:
    get: { summary: 获取通知列表 }
  /api/health-knowledge:
    get: { summary: 获取健康知识列表 }
  /api/assessments:
    get: { summary: 获取测评列表 }
    post: { summary: 创建测评 }
  /api/consultations:
    get: { summary: 获取咨询列表 }
    post: { summary: 创建咨询预约 }
  /api/psychologists:
    get: { summary: 获取心理老师列表 }
  /api/banners:
    get: { summary: 获取轮播图列表 }
"""

# 剩余模块列表（根据已有代码推断）
REMAINING_MODULES = [
    "心理老师管理与轮播图管理",
    "系统配置与数据统计",
]


def scan_existing_files(project_dir: str) -> list:
    """扫描已有 Java/前端文件，构建契约池"""
    contract_files = []
    key_dirs = ["entity", "dto", "repository", "common", "util", "config", "exception"]

    for root, dirs, files in os.walk(project_dir):
        for fname in files:
            if not fname.endswith(".java"):
                continue
            rel = os.path.relpath(os.path.join(root, fname), project_dir).replace("\\", "/")
            if any(k in rel for k in key_dirs):
                try:
                    with open(os.path.join(root, fname), "r", encoding="utf-8") as f:
                        content = f.read()
                    contract_files.append({"file_path": rel, "content": content})
                except Exception:
                    pass
    return contract_files


def main():
    print("[Resume] 扫描已有契约文件...")
    contract_files = scan_existing_files(PROJECT_DIR)
    print(f"[Resume] 发现 {len(contract_files)} 个契约文件")

    coder = CoderAgent(
        tech_stack="java",
        project_name=PROJECT_NAME,
        db_schema=DB_SCHEMA,
        api_contract=API_CONTRACT,
    )

    # 加载系统提示词
    system_prompt = prompts.load(
        "coder_system",
        tech_stack_name=TECH_STACKS["java"]["name"],
        project_name_lower=PROJECT_NAME.lower().replace(" ", "_"),
    )

    for i, module in enumerate(REMAINING_MODULES, 7):
        print(f"\n[Resume] 生成模块 {i}/9: {module}")

        contract_hint = coder._extract_contracts(contract_files) if contract_files else ""
        existing_paths = [f["file_path"] for f in contract_files]

        files = coder._generate_module_files(
            module, system_prompt,
            existing_files=existing_paths,
            contract_hint=contract_hint
        )
        print(f"[Resume] {module} 完成: {len(files)} 个文件")

        # 更新契约池
        for f in files:
            if any(x in f["file_path"] for x in [
                "common/", "entity/", "dto/", "repository/", "util/", "config/", "exception/"
            ]):
                contract_files.append(f)

    # 后处理
    coder._post_process_java_files()
    print("\n[Resume] 代码生成完成！")


if __name__ == "__main__":
    main()
