"""
全局配置：模型路由、技术栈、路径配置
支持三层覆盖：代码默认值 → .env 覆盖 → 运行时手动覆盖
"""
import os
from dotenv import load_dotenv
from typing import Dict, Optional

load_dotenv()

# ==================== 路径配置 ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPTS_DIR = os.path.join(BASE_DIR, "prompts")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
WORKSPACE_DIR = os.path.join(BASE_DIR, "workspace")

# ==================== LLM 提供商配置 ====================
PROVIDER_CONFIG = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
    },
}

# ==================== Agent 默认模型配置 ====================
DEFAULT_MODELS = {
    "pm": {
        "provider": "deepseek",
        "model": "deepseek-v4-pro",
        "temperature": 0.2,
        "max_tokens": 4096,
    },
    "architect": {
        "provider": "deepseek",
        "model": "deepseek-v4-pro",
        "temperature": 0.1,
        "max_tokens": 16384,
    },
    "coder": {
        "provider": "deepseek",
        "model": "deepseek-v4-pro",
        "temperature": 0.1,
        "max_tokens": 4096,
    },
    "builder": {
        "provider": "deepseek",
        "model": "deepseek-v4-pro",
        "temperature": 0.0,
        "max_tokens": 4096,
    },
    "test": {
        "provider": "deepseek",
        "model": "deepseek-v4-pro",
        "temperature": 0.2,
        "max_tokens": 4096,
    },
    "validator": {
        "provider": "deepseek",
        "model": "deepseek-v4-pro",
        "temperature": 0.1,
        "max_tokens": 4096,
    },
}


def get_agent_model_config(agent_name: str, override: Optional[Dict] = None) -> Dict:
    """
    获取 Agent 模型配置，支持三层覆盖：
    1. 代码默认值
    2. .env 环境变量覆盖
    3. 运行时手动覆盖
    """
    config = DEFAULT_MODELS.get(agent_name, DEFAULT_MODELS["coder"]).copy()

    # 第2层：.env 覆盖
    env_provider = os.getenv(f"{agent_name.upper()}_MODEL_PROVIDER")
    env_model = os.getenv(f"{agent_name.upper()}_MODEL_NAME")
    env_temp = os.getenv(f"{agent_name.upper()}_TEMPERATURE")

    if env_provider:
        config["provider"] = env_provider
    if env_model:
        config["model"] = env_model
    if env_temp:
        config["temperature"] = float(env_temp)

    # 第3层：运行时手动覆盖
    if override:
        config.update(override)

    return config


def get_llm_client(config: Dict):
    """根据配置创建 LangChain LLM 客户端
    底层 HTTP 超时：连接 10s，读取 120s，写入 30s
    防止服务端静默挂起导致无限等待
    """
    from langchain_openai import ChatOpenAI
    import httpx

    provider = config["provider"]
    provider_cfg = PROVIDER_CONFIG.get(provider, PROVIDER_CONFIG["deepseek"])
    api_key = os.getenv(provider_cfg["api_key_env"])

    if not api_key:
        raise ValueError(
            f"缺少 API Key: 请设置环境变量 {provider_cfg['api_key_env']}"
        )

    # 底层 HTTP 超时配置：连接10s + 读取1800s(30min) + 写入30s
    timeout = httpx.Timeout(1800.0, connect=10, read=1800, write=30)
    http_client = httpx.Client(timeout=timeout)

    return ChatOpenAI(
        model=config["model"],
        base_url=provider_cfg["base_url"],
        api_key=api_key,
        temperature=config["temperature"],
        max_tokens=config["max_tokens"],
        timeout=1800,
        max_retries=2,
        http_client=http_client,
    )


# ==================== 技术栈配置 ====================
TECH_STACKS = {
    "java": {
        "name": "Java + Vue3 + 微信小程序",
        "backend": "springboot",
        "frontend": "vue3",
        "miniapp": "wechat",
        "database": "mysql",
        "template_dir": "java-springboot",
    },
    "python": {
        "name": "Python + Vue3 + 微信小程序",
        "backend": "fastapi",
        "frontend": "vue3",
        "miniapp": "wechat",
        "database": "mysql",
        "template_dir": "python-fastapi",
    },
}
