"""
从 OpenAPI YAML + SQL Schema 中提取模块级开发契约
用逐行解析代替复杂正则，避免回溯问题
"""
import re
from typing import Dict, List, Any


def extract_module_contracts(api_yaml: str, db_schema: str, modules: List[dict]) -> Dict[str, str]:
    paths = _extract_paths_simple(api_yaml)
    schemas = _extract_schemas_simple(api_yaml)
    tables = _extract_tables_simple(db_schema)

    module_contracts = {}
    for module in modules:
        module_name = module.get("name", "")
        entities = module.get("entities", [])
        module_key = _module_name_to_key(module_name)

        lines = [f"【模块：{module_name}】"]

        # 实体
        lines.append("实体：")
        entity_found = False
        for entity in entities:
            candidates = [
                _entity_to_table(entity),
                _entity_to_table(entity).rstrip('s'),
                _entity_to_table(entity) + 's',
                _entity_to_table(entity) + '_table',
            ]
            for cand in candidates:
                if cand in tables:
                    fields = tables[cand]
                    field_strs = [f"{f['java_name']}:{f['java_type']}" for f in fields]
                    entity_class = _to_pascal_case(cand)
                    lines.append(f"  {entity_class}: [{', '.join(field_strs)}]")
                    entity_found = True
                    break
        if not entity_found:
            lines.append("  （根据数据库 Schema 推断）")

        # DTO
        lines.append("DTO：")
        dto_found = False
        for schema_name, schema_def in schemas.items():
            if _is_related(schema_name, module_key):
                props = schema_def.get("properties", {})
                required = schema_def.get("required", [])
                field_strs = []
                for prop_name, prop_def in props.items():
                    ptype = prop_def.get("type", "string")
                    java_type = _openapi_type_to_java(ptype)
                    req = "(required)" if prop_name in required else ""
                    field_strs.append(f"{prop_name}:{java_type}{req}")
                if field_strs:
                    lines.append(f"  {schema_name}: [{', '.join(field_strs)}]")
                    dto_found = True
        if not dto_found:
            lines.append("  （根据 API 契约推断）")

        # Service 方法
        lines.append("Service接口：")
        method_found = False
        for pd in paths:
            if _is_related(pd.get("operationId", ""), module_key) or _is_related(pd.get("path", ""), module_key):
                op = pd["operationId"]
                params = []
                for param in pd.get("parameters", []):
                    pname = param.get("name", "")
                    ptype = param.get("schema", {}).get("type", "string")
                    params.append(f"{_openapi_type_to_java(ptype)} {pname}")
                if pd.get("requestBody"):
                    params.append(f"{pd['requestBody']} request")
                param_str = ", ".join(params)
                ret = pd.get("responseRef", "void")
                lines.append(f"  - {op}({param_str}): {ret}")
                method_found = True
        if not method_found:
            lines.append("  （根据功能模块推断）")

        # Controller
        lines.append("Controller：")
        ctrl_found = False
        for pd in paths:
            if _is_related(pd.get("operationId", ""), module_key) or _is_related(pd.get("path", ""), module_key):
                method = pd["method"].upper()
                path = pd["path"]
                op = pd["operationId"]
                lines.append(f"  - {method} {path} → {op}")
                ctrl_found = True
        if not ctrl_found:
            lines.append("  （根据功能模块推断）")

        module_contracts[module_name] = "\n".join(lines)

    return module_contracts


def _extract_paths_simple(api_yaml: str) -> List[dict]:
    """逐行解析 YAML paths"""
    paths = []
    lines = api_yaml.split('\n')
    in_paths = False
    current_path = ""
    current_method = ""
    current_block = []

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped == "paths:":
            in_paths = True
            i += 1
            continue

        if not in_paths:
            i += 1
            continue

        # 检测 path 行 (2空格缩进 + /xxx:)
        path_match = re.match(r'^  (/[^:]+):\s*$', line)
        if path_match:
            current_path = path_match.group(1)
            i += 1
            continue

        # 检测方法行 (4空格缩进 + get/post/put/delete/patch:)
        method_match = re.match(r'^    (get|post|put|delete|patch):\s*$', line, re.IGNORECASE)
        if method_match and current_path:
            current_method = method_match.group(1).lower()
            current_block = []
            i += 1
            # 收集方法块直到下一个同层级或更高级别
            while i < len(lines):
                next_line = lines[i]
                # 下一个方法、下一个 path、或新的顶级key
                if re.match(r'^    (get|post|put|delete|patch):\s*$', next_line, re.IGNORECASE):
                    break
                if re.match(r'^  /[^:]+:\s*$', next_line):
                    break
                if re.match(r'^\w+:', next_line):
                    break
                current_block.append(next_line)
                i += 1

            # 解析方法块
            method_text = '\n'.join(current_block)

            op_id = ""
            m = re.search(r'operationId:\s*["\']?([A-Za-z]\w+)', method_text, re.IGNORECASE)
            if m:
                op_id = m.group(1)

            params = []
            # 简单提取 parameters
            j = 0
            block_lines = current_block
            while j < len(block_lines):
                pl = block_lines[j].strip()
                if pl.startswith('- name:'):
                    pname = pl.replace('- name:', '').strip()
                    # 向后找 in 和 type
                    p_in = "query"
                    p_type = "string"
                    k = j + 1
                    while k < len(block_lines) and block_lines[k].startswith('      '):
                        kl = block_lines[k].strip()
                        if kl.startswith('in:'):
                            p_in = kl.replace('in:', '').strip()
                        if kl.startswith('type:'):
                            p_type = kl.replace('type:', '').strip()
                        k += 1
                    params.append({"name": pname, "in": p_in, "schema": {"type": p_type}})
                    j = k
                    continue
                j += 1

            req_body = ""
            # 只在 requestBody 块内搜索 $ref
            rb_block_match = re.search(r'requestBody:\s*\n((?:\s+.*\n)+?)(?=^\s+\w+:|\Z)', method_text, re.MULTILINE)
            if rb_block_match:
                rb_m = re.search(r'\$ref:\s*[\'"]?#?/components/schemas/([^\'"\s]+)', rb_block_match.group(1))
                if rb_m:
                    req_body = rb_m.group(1)

            resp_ref = "void"
            # 找 responses 块中的第一个 $ref
            resp_m = re.search(r'responses:\s*\n(?:\s+.*\n)*?\s+\$ref:\s*[\'"]?#?/components/schemas/([^\'"\s]+)', method_text)
            if resp_m:
                resp_ref = resp_m.group(1)

            paths.append({
                "path": current_path,
                "method": current_method,
                "operationId": op_id,
                "parameters": params,
                "requestBody": req_body,
                "responseRef": resp_ref,
            })
            continue

        i += 1

    return paths


def _extract_schemas_simple(api_yaml: str) -> Dict[str, dict]:
    """逐行解析 schemas"""
    schemas = {}
    lines = api_yaml.split('\n')
    in_schemas = False
    current_schema = ""
    current_block = []

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped == "schemas:":
            in_schemas = True
            i += 1
            continue

        if not in_schemas:
            i += 1
            continue

        # 检测 schema 名 (4空格缩进 + Name:)
        schema_match = re.match(r'^    (\w+):\s*$', line)
        if schema_match:
            if current_schema and current_block:
                schemas[current_schema] = _parse_schema_block(current_block)
            current_schema = schema_match.group(1)
            current_block = []
            i += 1
            continue

        if current_schema:
            # 检测是否到了下一个 schema 或顶层
            if re.match(r'^    \w+:\s*$', line) or re.match(r'^\w+:', line):
                if current_schema and current_block:
                    schemas[current_schema] = _parse_schema_block(current_block)
                current_schema = ""
                current_block = []
                continue
            current_block.append(line)

        i += 1

    if current_schema and current_block:
        schemas[current_schema] = _parse_schema_block(current_block)

    return schemas


def _parse_schema_block(block: List[str]) -> dict:
    """解析单个 schema 的 block"""
    props = {}
    required = []
    in_props = False
    current_prop = ""

    i = 0
    while i < len(block):
        line = block[i]
        stripped = line.strip()

        if stripped == "properties:":
            in_props = True
            i += 1
            continue

        if not in_props:
            if stripped.startswith('required:'):
                # 收集 required 字段
                j = i + 1
                while j < len(block) and block[j].startswith('      - '):
                    req_field = block[j].strip().replace('- ', '')
                    required.append(req_field)
                    j += 1
                i = j
                continue
            i += 1
            continue

        # 检测属性名 (8空格缩进)
        prop_match = re.match(r'^        (\w+):\s*$', line)
        if prop_match:
            current_prop = prop_match.group(1)
            # 向后找 type (10空格缩进)
            ptype = "string"
            j = i + 1
            while j < len(block) and (block[j].startswith('          ') or block[j].strip() == ''):
                pl = block[j].strip()
                if pl.startswith('type:'):
                    ptype = pl.replace('type:', '').strip()
                j += 1
            props[current_prop] = {"type": ptype}
            i = j
            continue

        # 检测是否到了 properties 之外 (回到6空格或更少)
        if re.match(r'^      \w+:', line) or re.match(r'^    \w+:', line) or re.match(r'^  \w+:', line):
            in_props = False
            i += 1
            continue

        i += 1

    return {"properties": props, "required": required}


def _extract_tables_simple(db_schema: str) -> Dict[str, List[dict]]:
    """提取 SQL 表字段 - 用字符串分割避免正则回溯"""
    tables = {}
    # 找到每个 CREATE TABLE 的起止位置
    for match in re.finditer(r'CREATE\s+TABLE\s+(\w+)\s*\(', db_schema, re.IGNORECASE):
        table_name = match.group(1)
        start = match.end()  # 括号之后的位置
        # 找到匹配的结束括号
        depth = 1
        pos = start
        while pos < len(db_schema) and depth > 0:
            if db_schema[pos] == '(':
                depth += 1
            elif db_schema[pos] == ')':
                depth -= 1
            pos += 1
        body = db_schema[start:pos-1]

        fields = []
        for line in body.split('\n'):
            line = line.strip()
            if not line or line.startswith('PRIMARY') or line.startswith('FOREIGN') or line.startswith('INDEX') or line.startswith('UNIQUE') or line.startswith('KEY') or line.startswith('CONSTRAINT'):
                continue
            fm = re.match(r'(?:`?)(\w+)(?:`?)\s+(\w+)', line)
            if fm:
                col_name = fm.group(1)
                col_type = fm.group(2).upper()
                java_name = _snake_to_camel(col_name)
                java_type = _sql_type_to_java(col_type)
                fields.append({"name": col_name, "java_name": java_name, "java_type": java_type})
        if fields:
            tables[table_name] = fields
    return tables


def _module_name_to_key(name: str) -> str:
    return name.replace("与", "").replace("管理", "").replace("流程", "").lower()


def _entity_to_table(entity: str) -> str:
    mapping = {
        "用户": "user", "角色": "role", "权限": "permission",
        "商品": "product", "商品分类": "category", "商品图片": "product_image",
        "订单": "order", "交易记录": "trade_record", "支付流水": "payment_flow",
        "消息": "message", "通知": "notification",
        "管理员": "admin", "操作日志": "operation_log", "系统配置": "system_config",
    }
    return mapping.get(entity, entity.lower().replace(" ", "_"))


def _to_pascal_case(snake: str) -> str:
    return "".join(w.capitalize() for w in snake.split("_"))


def _snake_to_camel(snake: str) -> str:
    parts = snake.split("_")
    return parts[0] + "".join(w.capitalize() for w in parts[1:])


def _sql_type_to_java(sql_type: str) -> str:
    mapping = {
        "BIGINT": "Long", "INT": "Integer", "INTEGER": "Integer",
        "VARCHAR": "String", "TEXT": "String", "CHAR": "String",
        "DECIMAL": "BigDecimal", "DOUBLE": "Double", "FLOAT": "Float",
        "BOOLEAN": "Boolean", "TINYINT": "Integer", "DATETIME": "LocalDateTime",
        "TIMESTAMP": "LocalDateTime", "DATE": "LocalDateTime", "JSON": "String",
    }
    return mapping.get(sql_type.upper(), "String")


def _openapi_type_to_java(otype: str) -> str:
    mapping = {
        "string": "String", "integer": "Long", "number": "BigDecimal",
        "boolean": "Boolean", "array": "List",
    }
    return mapping.get(otype.lower(), "String")


def _is_related(name: str, module_key: str) -> bool:
    name_lower = name.lower()
    keywords = module_key.replace("资源", "").replace("通知", "消息").split("与")
    for kw in keywords:
        kw = kw.strip()
        if len(kw) >= 2 and kw in name_lower:
            return True
    # 中英文映射表
    mappings = {
        "用户": ["user", "auth", "login", "register", "password", "token"],
        "权限": ["user", "auth", "login", "register"],
        "分类": ["category", "categories", "type"],
        "账单": ["bill", "bills", "record", "records", "transaction", "amount", "income", "expense"],
        "记录": ["bill", "bills", "record", "records", "transaction", "amount"],
        "查询": ["query", "search", "filter", "list", "get", "find"],
        "统计": ["stat", "stats", "summary", "report", "analytics", "chart", "trend"],
        "报表": ["stat", "stats", "summary", "report", "analytics"],
        "商品": ["product", "products", "goods", "item"],
        "订单": ["order", "orders", "trade", "pay", "payment"],
        "消息": ["message", "messages", "notification", "notice"],
        "系统": ["admin", "system", "config", "setting"],
    }
    for cn_kw, en_kws in mappings.items():
        if cn_kw in module_key:
            for en_kw in en_kws:
                if en_kw in name_lower:
                    return True
    return False
