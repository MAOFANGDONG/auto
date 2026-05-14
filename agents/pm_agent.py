"""
PM Agent：项目经理
负责解析开题报告，提取结构化需求

关键改进（v2）：
1. 丰富 JSON Schema：modules 增加 core_features/entities/estimated_apis/module_type/dependencies
2. 全局增加 entity_relationships/actor_permissions/data_flow/key_business_rules
3. 智能合并：保留更多上下文，不粗暴截断
4. 质量验证：输出前做完整性检查
"""
import json
import re
from typing import Dict, List, Any
from loguru import logger

from config import get_agent_model_config, get_llm_client
from prompts.prompt_loader import prompts
from tools.retry_wrapper import retry_with_fallback


class PMAgent:
    """需求解析 Agent - v2 增强版"""

    def __init__(self, model_override: Dict = None):
        config = get_agent_model_config("pm", override=model_override)
        self.llm = get_llm_client(config)
        logger.info(f"[PM Agent] 使用模型: {config['provider']}/{config['model']}")

    @retry_with_fallback(
        max_retries=3,
        delay=3,
        fallback_value=None,
    )
    def parse(self, report_text: str) -> Dict:
        """
        解析开题报告，返回结构化需求
        :param report_text: 开题报告原始文本
        :return: 包含丰富字段的字典
        """
        # 清理文本
        report_text = report_text.strip()
        if len(report_text) > 20000:
            report_text = report_text[:20000] + "\n...[内容过长，已截断，保留前 20000 字]"

        # 加载 Prompt 模板
        prompt = prompts.load("pm_agent", report_text=report_text)

        # 调用 LLM（带重试）
        logger.info("[PM Agent] 调用 LLM 解析...")
        response = self.llm.invoke([("user", prompt)])
        content = response.content

        # 提取 JSON
        result = self._extract_json(content)

        if result is None:
            logger.error("[PM Agent] JSON 提取失败，使用 fallback")
            result = self._create_fallback_result(report_text)

        # 后处理：补全默认值 + 规范化
        result = self._post_process(result)

        # 质量验证
        quality = self._validate_result(result)
        logger.info(f"[PM Agent] 解析完成: {result.get('project_name', 'unknown')}, "
                    f"{len(result.get('modules', []))} 个模块, 质量评分: {quality['score']}/10")

        if quality["issues"]:
            logger.warning(f"[PM Agent] 质量检查发现问题: {quality['issues']}")

        return result

    def _extract_json(self, text: str) -> Dict:
        """从 LLM 输出中提取 JSON，多层 fallback"""
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试提取代码块中的 JSON
        patterns = [
            r"```json\s*(.*?)\s*```",
            r"```\s*(.*?)\s*```",
            r"(\{[\s\S]*?\})\s*$",  # 从最后一个 { 开始匹配
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            for match in matches:
                try:
                    return json.loads(match)
                except json.JSONDecodeError:
                    continue

        # 尝试修复常见的 JSON 问题
        fixed = self._fix_json(text)
        if fixed:
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                pass

        return None

    def _fix_json(self, text: str) -> str:
        """尝试修复常见的 JSON 格式问题"""
        # 找到最外层的大括号
        start = text.find('{')
        end = text.rfind('}')
        if start == -1 or end == -1 or start >= end:
            return None

        json_str = text[start:end+1]

        # 修复 trailing comma
        json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)

        # 修复单引号
        json_str = json_str.replace("'", '"')

        # 修复无引号 key（简单情况）
        json_str = re.sub(r'(\{|,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1 "\2":', json_str)

        return json_str

    def _create_fallback_result(self, report_text: str) -> Dict:
        """LLM 完全失败时的 fallback，基于关键词提取"""
        logger.warning("[PM Agent] 使用关键词提取 fallback")

        # 提取项目名
        title_match = re.search(r'[《"]?(.*?)[》"]?\s*(?:的|设计|实现|系统)', report_text[:200])
        project_title = title_match.group(1) if title_match else "未命名项目"
        project_name = re.sub(r'[^a-zA-Z0-9_]', '_', project_title.lower())[:30].strip('_')

        # 提取技术栈
        tech_hint = ""
        if "spring" in report_text.lower():
            tech_hint = "基于SpringBoot"
        elif "django" in report_text.lower():
            tech_hint = "基于Django"
        elif "fastapi" in report_text.lower():
            tech_hint = "基于FastAPI"

        # 提取功能点
        features = re.findall(r'[\d一二三四五六七八九十]+[\.、]\s*(.+?)(?:[：:；]|\n)', report_text)

        return {
            "project_name": project_name or "unknown_project",
            "project_title": project_title,
            "tech_stack_hint": tech_hint,
            "business_overview": f"基于开题报告提取的项目：{project_title}",
            "modules": [
                {
                    "name": "核心业务管理",
                    "description": "系统核心业务功能",
                    "core_features": features[:6] if features else ["基础功能"],
                    "entities": ["用户"],
                    "estimated_apis": 10,
                    "module_type": "core",
                    "dependencies": []
                }
            ],
            "entities": ["用户"],
            "entity_relationships": [],
            "actors": ["用户", "管理员"],
            "actor_permissions": {"用户": ["基础操作"], "管理员": ["所有权限"]},
            "constraints": [],
            "complexity": "medium",
            "data_flow": "用户操作 → 系统处理 → 数据存储",
            "key_business_rules": [],
            "_fallback": True,
        }

    def _post_process(self, result: Dict) -> Dict:
        """后处理：补全默认值、规范化、智能合并"""
        # 基础字段
        result.setdefault("project_name", "unknown_project")
        result.setdefault("project_title", result["project_name"])
        result.setdefault("tech_stack_hint", "")
        result.setdefault("business_overview", f"项目：{result.get('project_title', '')}")

        # 模块处理
        modules = result.get("modules", [])
        if not modules:
            modules = [{
                "name": "核心业务",
                "description": "系统核心功能",
                "core_features": ["基础功能"],
                "entities": ["用户"],
                "estimated_apis": 10,
                "module_type": "core",
                "dependencies": []
            }]

        # 智能合并（如果模块数 > 7）
        if len(modules) > 7:
            modules = self._smart_merge(modules)
            logger.info(f"[PM Agent] 智能合并后为 {len(modules)} 个模块")

        # 规范化每个模块
        for m in modules:
            m.setdefault("name", "未命名模块")
            m.setdefault("description", m["name"])
            m.setdefault("core_features", [])
            m.setdefault("entities", [])
            m.setdefault("estimated_apis", 8)
            m.setdefault("module_type", "core")
            m.setdefault("dependencies", [])

            # 确保 core_features 是列表
            if isinstance(m["core_features"], str):
                m["core_features"] = [f.strip() for f in m["core_features"].split(",") if f.strip()]

            # 确保 estimated_apis 是数字
            try:
                m["estimated_apis"] = int(m["estimated_apis"])
            except (ValueError, TypeError):
                m["estimated_apis"] = 8

            # 如果 core_features 为空，从 description 中提取
            if not m["core_features"] and m["description"]:
                # 按常见分隔符拆分
                parts = re.split(r'[，、；,;]', m["description"])
                m["core_features"] = [p.strip() for p in parts if len(p.strip()) > 2][:6]

            # 确保 entities 是列表
            if isinstance(m["entities"], str):
                m["entities"] = [e.strip() for e in m["entities"].split(",") if e.strip()]

        result["modules"] = modules

        # 全局字段
        result.setdefault("entities", [])
        result.setdefault("entity_relationships", [])
        result.setdefault("actors", ["用户", "管理员"])
        result.setdefault("actor_permissions", {})
        result.setdefault("constraints", [])
        result.setdefault("complexity", "medium")
        result.setdefault("data_flow", "")
        result.setdefault("key_business_rules", [])

        # 如果 actor_permissions 为空，填充默认值
        if not result["actor_permissions"]:
            for actor in result["actors"]:
                result["actor_permissions"][actor] = ["基础操作"]
            if result["actors"]:
                result["actor_permissions"][result["actors"][-1]] = ["所有权限"]

        # 如果 entities 为空，从 modules 中收集
        if not result["entities"]:
            all_entities = set()
            for m in modules:
                all_entities.update(m.get("entities", []))
            result["entities"] = list(all_entities)

        return result

    def _smart_merge(self, modules: List[Dict]) -> List[Dict]:
        """智能合并模块，保留更多信息"""
        merge_rules = {
            "用户与权限管理": {
                "keywords": ["用户", "权限", "认证", "登录", "注册", "账户", "角色", "基础数据", "学校", "班级", "年级", "部门"],
                "type": "core",
            },
            "内容管理": {
                "keywords": ["健康", "知识", "文章", "内容", "通知", "公告", "轮播", "banner", "推送", "消息", "资讯"],
                "type": "support",
            },
            "商品资源管理": {
                "keywords": ["商品", "物品", "资源", "产品", "分类", "库存", "上架", "下架"],
                "type": "core",
            },
            "交易流程管理": {
                "keywords": ["订单", "交易", "支付", "购买", "销售", "流程", "下单", "退款"],
                "type": "core",
            },
            "测评与档案管理": {
                "keywords": ["测评", "考试", "问卷", "测试", "评估", "量表", "学生", "档案", "记录", "成绩", "答题", "试卷"],
                "type": "core",
            },
            "咨询预约管理": {
                "keywords": ["咨询", "预约", "心理", "老师", "辅导", "沟通", "问诊", "治疗", "医生", "挂号"],
                "type": "core",
            },
            "数据统计分析": {
                "keywords": ["统计", "报表", "分析", "图表", "可视化", "大数据", "数据挖掘"],
                "type": "support",
            },
            "消息通知管理": {
                "keywords": ["消息", "通知", "提醒", "推送", "站内信", "邮件", "短信"],
                "type": "support",
            },
            "系统管理": {
                "keywords": ["系统", "配置", "日志", "字典", "参数", "设置", "后台", "管理员", "审计"],
                "type": "admin",
            },
        }

        # 分类收集
        buckets = {k: [] for k in merge_rules}
        buckets["其他业务"] = []

        for m in modules:
            name = m.get("name", "")
            desc = m.get("description", "")
            features = " ".join(m.get("core_features", []))
            text = f"{name} {desc} {features}"

            matched = False
            for big_name, rule in merge_rules.items():
                if any(kw in text for kw in rule["keywords"]):
                    buckets[big_name].append(m)
                    matched = True
                    break
            if not matched:
                buckets["其他业务"].append(m)

        # 构建合并后的模块
        result = []
        for big_name, sub_modules in buckets.items():
            if not sub_modules:
                continue

            # 合并功能点
            all_features = []
            all_entities = []
            total_apis = 0

            for m in sub_modules:
                all_features.extend(m.get("core_features", []))
                all_entities.extend(m.get("entities", []))
                total_apis += m.get("estimated_apis", 8)

            # 去重并限制数量
            unique_features = []
            seen = set()
            for f in all_features:
                key = f[:20]  # 前20字去重
                if key not in seen and len(unique_features) < 8:
                    seen.add(key)
                    unique_features.append(f)

            unique_entities = list(dict.fromkeys(all_entities))[:5]

            # 合并描述（取最长的那个作为基础，或拼接）
            descriptions = [m.get("description", "") for m in sub_modules if m.get("description")]
            if descriptions:
                # 如果有长描述，取最长的；否则拼接
                best_desc = max(descriptions, key=len)
                if len(best_desc) < 30 and len(descriptions) > 1:
                    combined = "；".join(d[:40] for d in descriptions)
                    best_desc = combined[:120]
            else:
                best_desc = big_name

            result.append({
                "name": big_name,
                "description": best_desc[:150],
                "core_features": unique_features if unique_features else [f"{big_name}相关功能"],
                "entities": unique_entities if unique_entities else ["用户"],
                "estimated_apis": min(total_apis, 20),
                "module_type": merge_rules.get(big_name, {}).get("type", "core"),
                "dependencies": [],
            })

        return result

    def _validate_result(self, result: Dict) -> Dict:
        """验证结果质量，返回评分和问题列表"""
        issues = []
        score = 10

        modules = result.get("modules", [])

        # 1. 模块数量检查
        if len(modules) < 4:
            issues.append(f"模块数过少({len(modules)}个)，可能合并太粗")
            score -= 2
        elif len(modules) > 7:
            issues.append(f"模块数过多({len(modules)}个)，可能合并太细")
            score -= 2

        # 2. 模块字段完整性
        for i, m in enumerate(modules):
            if not m.get("core_features"):
                issues.append(f"模块[{i}] {m.get('name', '?')} 缺少 core_features")
                score -= 1
            if not m.get("description"):
                issues.append(f"模块[{i}] {m.get('name', '?')} 缺少 description")
                score -= 1
            if m.get("estimated_apis", 0) <= 0:
                issues.append(f"模块[{i}] {m.get('name', '?')} estimated_apis 不合理")
                score -= 0.5

        # 3. 实体一致性
        all_module_entities = set()
        for m in modules:
            all_module_entities.update(m.get("entities", []))
        global_entities = set(result.get("entities", []))
        if all_module_entities - global_entities:
            issues.append(f"模块实体未在全局 entities 中体现: {all_module_entities - global_entities}")
            score -= 1

        # 4. 角色权限
        actors = result.get("actors", [])
        permissions = result.get("actor_permissions", {})
        for actor in actors:
            if actor not in permissions:
                issues.append(f"角色 '{actor}' 缺少权限描述")
                score -= 0.5

        # 5. 关键字段
        if not result.get("business_overview"):
            issues.append("缺少 business_overview")
            score -= 1
        if not result.get("data_flow"):
            issues.append("缺少 data_flow")
            score -= 0.5

        return {
            "score": max(0, int(score)),
            "issues": issues,
            "module_count": len(modules),
            "total_estimated_apis": sum(m.get("estimated_apis", 0) for m in modules),
        }
