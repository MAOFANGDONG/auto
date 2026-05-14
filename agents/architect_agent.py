"""
Architect Agent：架构设计师（v2 拆分版）
拆分为两次 LLM 调用：
  1. Schema Agent：只生成数据库 Schema（SQL）
  2. API Agent：基于 Schema 生成 OpenAPI 契约（YAML）+ 项目结构
彻底解决单次输出截断导致 api.yaml 为空的问题。
"""
import json
import os
import re
from typing import Dict
from loguru import logger

from config import get_agent_model_config
from prompts.prompt_loader import prompts
from tools.retry_wrapper import retry_with_fallback
from tools.api_repair import repair_api_yaml


class ArchitectAgent:
    """架构设计 Agent - v2 拆分版"""

    def __init__(self, model_override: Dict = None):
        self.config = get_agent_model_config("architect", override=model_override)
        logger.info(f"[Architect Agent] 使用模型: {self.config['provider']}/{self.config['model']}")

    @retry_with_fallback(
        max_retries=3,
        delay=5,
        fallback_value={
            "db_schema": "CREATE TABLE users (id BIGINT PRIMARY KEY AUTO_INCREMENT, username VARCHAR(50) NOT NULL UNIQUE, password_hash VARCHAR(255) NOT NULL, nickname VARCHAR(50), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP);\nCREATE TABLE categories (id BIGINT PRIMARY KEY AUTO_INCREMENT, name VARCHAR(50) NOT NULL, type VARCHAR(20) NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);\nCREATE TABLE records (id BIGINT PRIMARY KEY AUTO_INCREMENT, user_id BIGINT NOT NULL, category_id BIGINT NOT NULL, amount DECIMAL(10,2) NOT NULL, type VARCHAR(20) NOT NULL, note TEXT, record_date DATE NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP);",
            "api_contract": "openapi: 3.0.0\ninfo:\n  title: Generated API\n  version: 1.0.0\npaths:\n  /api/auth/register:\n    post:\n      operationId: registerUser\n      summary: 用户注册\n  /api/auth/login:\n    post:\n      operationId: loginUser\n      summary: 登录",
            "project_structure": "src/main/java/com/example/demo/\n  entity/\n  controller/\n  service/\n  service/impl/\n  repository/\n  dto/\n  common/\n  config/\n  util/\n  exception/",
        },
    )
    def design(
        self,
        project_name: str,
        tech_stack: str,
        modules: list,
        requirements_summary: str,
    ) -> Dict[str, str]:
        """
        设计数据库和 API（拆分两阶段）
        :return: {"db_schema": "...", "api_contract": "...", "project_structure": "..."}
        """
        # 从 requirements_summary JSON 中提取丰富字段
        entities_str, actors_str, constraints_str, relationships_str = self._extract_from_requirements(
            requirements_summary
        )

        # ========== 阶段 1：生成数据库 Schema ==========
        logger.info("[Architect Agent] 阶段 1/2：生成数据库 Schema...")
        schema_prompt = prompts.load(
            "architect_schema",
            project_name=project_name,
            tech_stack=tech_stack,
            modules=str(modules),
            entities=entities_str,
            actors=actors_str,
            constraints=constraints_str,
            relationships=relationships_str,
        )
        schema_raw = self._call_api(schema_prompt)
        db_schema = self._extract_schema(schema_raw)

        if not db_schema.strip():
            logger.warning("[Architect Agent] Schema 为空，使用 fallback")
            db_schema = self._generate_fallback_schema(modules)

        logger.info(f"[Architect Agent] Schema 生成完成: {db_schema.count('CREATE TABLE')} 个表")

        # 保存阶段 1 输出用于调试
        debug_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workspace", "architect_debug")
        os.makedirs(debug_dir, exist_ok=True)
        with open(os.path.join(debug_dir, "schema_raw.txt"), "w", encoding="utf-8") as f:
            f.write(schema_raw)

        # ========== 阶段 2：基于 Schema 生成 API 契约 ==========
        logger.info("[Architect Agent] 阶段 2/2：基于 Schema 生成 API 契约...")
        api_prompt = prompts.load(
            "architect_api",
            project_name=project_name,
            tech_stack=tech_stack,
            modules=str(modules),
            entities=entities_str,
            db_schema=db_schema,
        )
        api_raw = self._call_api(api_prompt)
        api_result = self._parse_api_sections(api_raw)

        if not api_result.get("api_contract", "").strip():
            logger.warning("[Architect Agent] API 契约为空，使用 fallback")
            api_result["api_contract"] = "openapi: 3.0.0\ninfo:\n  title: Generated API\n  version: 1.0.0\npaths: {}"
        if not api_result.get("project_structure", "").strip():
            api_result["project_structure"] = "src/main/java/com/example/demo/\n  entity/\n  controller/\n  service/\n  repository/"

        # 保存阶段 2 原始输出用于调试
        with open(os.path.join(debug_dir, "api_raw.txt"), "w", encoding="utf-8") as f:
            f.write(api_raw)

        # ========== 阶段 3：验证并自动修复 API 契约 ==========
        api_contract = api_result.get("api_contract", "")
        if api_contract.strip() and db_schema.strip():
            logger.info("[Architect Agent] 阶段 3/3：验证并修复 API 契约...")
            try:
                repaired_api, repair_report = repair_api_yaml(api_contract, db_schema)
                api_contract = repaired_api
                logger.info(
                    f"[Architect Agent] API 修复报告: "
                    f"语法修复={repair_report.get('yaml_syntax_fixed', False)}, "
                    f"缺失 schemas={len(repair_report.get('missing_schemas', []))}, "
                    f"成功添加={len(repair_report.get('added_schemas', []))}, "
                    f"错误={len(repair_report.get('errors', []))}"
                )
                if repair_report.get('added_schemas'):
                    logger.info(f"[Architect Agent] 自动推导 schemas: {repair_report['added_schemas']}")
                if repair_report.get('errors'):
                    logger.warning(f"[Architect Agent] 修复错误: {repair_report['errors']}")
                # 保存修复后的输出
                with open(os.path.join(debug_dir, "api_repaired.yaml"), "w", encoding="utf-8") as f:
                    f.write(api_contract)
            except Exception as e:
                logger.warning(f"[Architect Agent] API 修复失败，使用原始结果: {e}")

        logger.info("[Architect Agent] 架构设计完成")
        return {
            "db_schema": db_schema,
            "api_contract": api_contract,
            "project_structure": api_result.get("project_structure", ""),
        }

    def _extract_from_requirements(self, requirements_summary: str) -> tuple:
        """从 requirements_summary JSON 中提取关键字段"""
        try:
            data = json.loads(requirements_summary)
        except (json.JSONDecodeError, ValueError):
            return "", "", "", ""

        entities = data.get("entities", [])
        actors = data.get("actors", [])
        constraints = data.get("constraints", [])
        relationships = data.get("entity_relationships", [])
        data_flow = data.get("data_flow", "")
        business_rules = data.get("key_business_rules", [])

        parts = []
        if entities:
            parts.append(f"核心实体: {', '.join(entities)}")
        if relationships:
            parts.append(f"实体关系: {', '.join(relationships)}")
        if data_flow:
            parts.append(f"数据流: {data_flow}")
        if business_rules:
            parts.append(f"业务规则: {'; '.join(business_rules)}")
        relationships_str = "\n".join(parts)

        return (
            ", ".join(entities) if entities else "",
            ", ".join(actors) if actors else "",
            "; ".join(constraints) if constraints else "",
            relationships_str,
        )

    def _generate_fallback_schema(self, modules: list) -> str:
        """根据模块列表生成一个最基础的 fallback schema"""
        tables = []
        tables.append(
            "CREATE TABLE users (id BIGINT PRIMARY KEY AUTO_INCREMENT, "
            "username VARCHAR(50) NOT NULL UNIQUE, password_hash VARCHAR(255) NOT NULL, "
            "nickname VARCHAR(50), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
            "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP);"
        )
        module_names = [m["name"] if isinstance(m, dict) else str(m) for m in modules]
        name_lower = " ".join(module_names).lower()
        if "分类" in name_lower or "类别" in name_lower or "category" in name_lower:
            tables.append(
                "CREATE TABLE categories (id BIGINT PRIMARY KEY AUTO_INCREMENT, "
                "name VARCHAR(50) NOT NULL, type VARCHAR(20) NOT NULL, "
                "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"
            )
        if "记录" in name_lower or "账单" in name_lower or "transaction" in name_lower or "record" in name_lower:
            tables.append(
                "CREATE TABLE records (id BIGINT PRIMARY KEY AUTO_INCREMENT, "
                "user_id BIGINT NOT NULL, category_id BIGINT, amount DECIMAL(10,2) NOT NULL, "
                "type VARCHAR(20) NOT NULL, note TEXT, record_date DATE NOT NULL, "
                "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
                "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP);"
            )
        if "订单" in name_lower or "order" in name_lower:
            tables.append(
                "CREATE TABLE orders (id BIGINT PRIMARY KEY AUTO_INCREMENT, buyer_id BIGINT NOT NULL, "
                "seller_id BIGINT NOT NULL, product_id BIGINT NOT NULL, status VARCHAR(20) DEFAULT 'PENDING', "
                "total_amount DECIMAL(10,2) NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
                "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP);"
            )
        if "商品" in name_lower or "产品" in name_lower or "product" in name_lower:
            tables.append(
                "CREATE TABLE products (id BIGINT PRIMARY KEY AUTO_INCREMENT, user_id BIGINT NOT NULL, "
                "title VARCHAR(200) NOT NULL, description TEXT, price DECIMAL(10,2) NOT NULL, "
                "status VARCHAR(20) DEFAULT 'AVAILABLE', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
                "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP);"
            )
        return "\n".join(tables)

    def _extract_schema(self, text: str) -> str:
        """从 LLM 输出中提取 SQL Schema"""
        # 策略1：去掉 Markdown 代码块标记
        cleaned = text.strip()
        if cleaned.startswith("```sql"):
            cleaned = cleaned[6:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        # 策略2：提取 CREATE TABLE 语句块
        create_tables = []
        for match in re.finditer(r'CREATE\s+TABLE\s+\w+\s*\([^;]+?\);', cleaned, re.IGNORECASE | re.DOTALL):
            create_tables.append(match.group(0))

        if create_tables:
            return "\n\n".join(create_tables)

        # 策略3：如果什么都没找到，返回原始内容（可能 LLM 已经输出了纯 SQL）
        return cleaned

    def _parse_api_sections(self, text: str) -> Dict[str, str]:
        """解析 API 和项目结构"""
        sections = {"api_contract": "", "project_structure": ""}

        # 策略1：用 === 分割
        text_clean = re.sub(r'^#.*===.*$', '', text, flags=re.MULTILINE)
        parts = re.split(r'===\s*(OPENAPI_CONTRACT|PROJECT_STRUCTURE)\s*===', text_clean, flags=re.IGNORECASE)
        key_map = {'openapi_contract': 'api_contract', 'project_structure': 'project_structure'}
        for i in range(1, len(parts), 2):
            key = key_map.get(parts[i].lower().replace(' ', '_'))
            if key and key in sections and i + 1 < len(parts):
                sections[key] = parts[i + 1].strip()

        # 策略2：Markdown 代码块回退
        if not sections["api_contract"]:
            yaml_match = re.search(r"```(?:yaml|yml)?\s*(openapi:\s*3\.0.*?)(?:```|$)", text, re.DOTALL | re.IGNORECASE)
            if yaml_match:
                sections["api_contract"] = yaml_match.group(1).strip()

        if not sections["project_structure"]:
            tree_match = re.search(r"(src[/\\].*?)(?:\n\n|\Z)", text, re.DOTALL)
            if tree_match:
                sections["project_structure"] = tree_match.group(1).strip()

        return sections

    def _call_api(self, prompt: str) -> str:
        """直接调用 OpenAI API，绕过 LangChain"""
        from openai import OpenAI
        import httpx

        provider_cfg = {
            "deepseek": {
                "base_url": "https://api.deepseek.com/v1",
                "api_key_env": "DEEPSEEK_API_KEY",
            },
            "openai": {
                "base_url": "https://api.openai.com/v1",
                "api_key_env": "OPENAI_API_KEY",
            },
        }.get(self.config["provider"], {"base_url": "https://api.deepseek.com/v1", "api_key_env": "DEEPSEEK_API_KEY"})

        api_key = os.getenv(provider_cfg["api_key_env"])
        if not api_key:
            raise ValueError(f"缺少 API Key: {provider_cfg['api_key_env']}")

        http_client = httpx.Client(timeout=httpx.Timeout(1800.0, connect=10, read=1800, write=30))

        client = OpenAI(
            base_url=provider_cfg["base_url"],
            api_key=api_key,
            timeout=120,
            max_retries=2,
            http_client=http_client,
        )

        response = client.chat.completions.create(
            model=self.config["model"],
            messages=[{"role": "user", "content": prompt}],
            temperature=self.config["temperature"],
            max_tokens=self.config["max_tokens"],
        )
        return response.choices[0].message.content
