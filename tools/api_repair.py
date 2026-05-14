"""
API Repair Tool: 自动修复 Architect Agent 生成的 api.yaml

核心能力：
1. 解析 SQL Schema，建立表→字段映射
2. 提取 api.yaml 中所有 $ref 引用和已定义 schemas
3. 基于命名约定自动推导缺失的 DTO schemas
4. 修复 YAML 语法截断问题

使用场景：LLM 生成 api.yaml 时因 token 限制导致 components/schemas 截断
"""

import re
from typing import Dict, List, Set, Tuple, Optional


class SQLSchemaParser:
    """解析 MySQL CREATE TABLE 语句"""

    TYPE_MAP = {
        'varchar': 'string', 'char': 'string', 'text': 'string',
        'longtext': 'string', 'mediumtext': 'string', 'tinytext': 'string',
        'int': 'integer', 'bigint': 'integer', 'tinyint': 'integer',
        'smallint': 'integer', 'mediumint': 'integer',
        'decimal': 'number', 'float': 'number', 'double': 'number',
        'boolean': 'boolean',
        'timestamp': 'string', 'datetime': 'string', 'date': 'string', 'time': 'string',
        'json': 'object',
    }

    TIME_FORMATS = {
        'timestamp': 'date-time', 'datetime': 'date-time',
        'date': 'date', 'time': 'time',
    }

    def parse(self, sql: str) -> Dict[str, Dict]:
        tables = {}
        pattern = re.compile(
            r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?(\w+)`?\s*\((.*?)\)\s*'
            r'(?:ENGINE|DEFAULT\s+CHARSET|CHARSET|COMMENT|=).*?;',
            re.IGNORECASE | re.DOTALL
        )
        for match in pattern.finditer(sql):
            table_name = match.group(1).lower()
            body = match.group(2)
            columns = self._parse_columns(body)
            comment_match = re.search(r"COMMENT\s*=\s*'([^']+)'", match.group(0), re.IGNORECASE)
            tables[table_name] = {
                'columns': columns,
                'comment': comment_match.group(1) if comment_match else '',
            }
        return tables

    def _parse_columns(self, body: str) -> List[Dict]:
        columns = []
        parts = self._split_columns(body)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if re.match(r'^(PRIMARY\s+KEY|FOREIGN\s+KEY|INDEX|UNIQUE\s+KEY|KEY|CONSTRAINT)\b', part, re.IGNORECASE):
                continue
            col = self._parse_single_column(part)
            if col:
                columns.append(col)
        return columns

    def _split_columns(self, body: str) -> List[str]:
        parts = []
        current = []
        depth = 0
        for char in body:
            if char == '(':
                depth += 1
                current.append(char)
            elif char == ')':
                depth -= 1
                current.append(char)
            elif char == ',' and depth == 0:
                parts.append(''.join(current))
                current = []
            else:
                current.append(char)
        if current:
            parts.append(''.join(current))
        return parts

    def _parse_single_column(self, line: str) -> Optional[Dict]:
        match = re.match(
            r'^`?(\w+)`?\s+(\w+)(?:\([^)]*\))?\s*',
            line, re.IGNORECASE
        )
        if not match:
            return None

        col_name = match.group(1)
        sql_type = match.group(2).lower()
        nullable = 'NOT NULL' not in line.upper()
        is_auto_increment = 'AUTO_INCREMENT' in line.upper()
        is_primary_key = 'PRIMARY KEY' in line.upper()
        comment_match = re.search(r"COMMENT\s+'([^']*)'", line, re.IGNORECASE)
        comment = comment_match.group(1) if comment_match else ''

        openapi_type = self.TYPE_MAP.get(sql_type, 'string')
        openapi_format = self.TIME_FORMATS.get(sql_type) if openapi_type == 'string' else None

        return {
            'name': col_name, 'sql_type': sql_type,
            'openapi_type': openapi_type, 'format': openapi_format,
            'nullable': nullable, 'comment': comment,
            'is_primary_key': is_primary_key, 'is_auto_increment': is_auto_increment,
        }


class DTODerivator:
    """基于 SQL schema 推导 OpenAPI DTO schemas"""

    SPECIAL_SCHEMAS = {
        'LoginRequest': {
            'type': 'object',
            'properties': {
                'username': {'type': 'string', 'description': '用户名'},
                'password': {'type': 'string', 'description': '密码'},
            },
            'required': ['username', 'password'],
        },
        'RegisterRequest': {
            'type': 'object',
            'properties': {
                'username': {'type': 'string', 'description': '用户名'},
                'password': {'type': 'string', 'description': '密码'},
                'nickname': {'type': 'string', 'description': '昵称'},
                'email': {'type': 'string', 'description': '邮箱'},
                'phone': {'type': 'string', 'description': '手机号'},
            },
            'required': ['username', 'password'],
        },
        'PasswordChangeRequest': {
            'type': 'object',
            'properties': {
                'oldPassword': {'type': 'string', 'description': '旧密码'},
                'newPassword': {'type': 'string', 'description': '新密码'},
            },
            'required': ['oldPassword', 'newPassword'],
        },
        'LoginResponse': {
            'type': 'object',
            'properties': {
                'token': {'type': 'string', 'description': 'JWT Token'},
                'refreshToken': {'type': 'string', 'description': '刷新Token'},
                'user': {'$ref': '#/components/schemas/UserDTO'},
            },
            'required': ['token'],
        },
        'MessageResponse': {
            'type': 'object',
            'properties': {
                'message': {'type': 'string', 'description': '提示消息'},
            },
            'required': ['message'],
        },
        'ErrorResponse': {
            'type': 'object',
            'properties': {
                'code': {'type': 'integer', 'description': '错误码'},
                'message': {'type': 'string', 'description': '错误信息'},
                'timestamp': {'type': 'string', 'format': 'date-time', 'description': '时间戳'},
                'path': {'type': 'string', 'description': '请求路径'},
            },
            'required': ['code', 'message'],
        },
        'PageParam': {
            'type': 'object',
            'properties': {
                'page': {'type': 'integer', 'default': 1, 'description': '页码，从1开始'},
                'size': {'type': 'integer', 'default': 10, 'description': '每页大小'},
            },
        },
        'SizeParam': {
            'type': 'object',
            'properties': {
                'size': {'type': 'integer', 'default': 10, 'description': '每页大小'},
            },
        },
        'BadRequest': {
            'type': 'object', 'properties': {'code': {'type': 'integer', 'default': 400}, 'message': {'type': 'string'}},
        },
        'Unauthorized': {
            'type': 'object', 'properties': {'code': {'type': 'integer', 'default': 401}, 'message': {'type': 'string'}},
        },
        'Forbidden': {
            'type': 'object', 'properties': {'code': {'type': 'integer', 'default': 403}, 'message': {'type': 'string'}},
        },
        'NotFound': {
            'type': 'object', 'properties': {'code': {'type': 'integer', 'default': 404}, 'message': {'type': 'string'}},
        },
        'ReviewActionRequest': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'enum': ['approve', 'reject'], 'description': '审核动作'},
                'reason': {'type': 'string', 'description': '原因'},
            },
            'required': ['action'],
        },
        'TradeOrderStatusRequest': {
            'type': 'object',
            'properties': {
                'status': {'type': 'string', 'enum': ['pending', 'confirmed', 'shipped', 'completed', 'cancelled'], 'description': '订单状态'},
            },
            'required': ['status'],
        },
        'StatisticDTO': {
            'type': 'object',
            'properties': {
                'userCount': {'type': 'integer', 'description': '用户总数'},
                'collectionCount': {'type': 'integer', 'description': '藏品总数'},
                'tradeCount': {'type': 'integer', 'description': '交易总数'},
                'exchangeCount': {'type': 'integer', 'description': '交换总数'},
                'postCount': {'type': 'integer', 'description': '帖子总数'},
                'newUserCountToday': {'type': 'integer', 'description': '今日新增用户'},
                'newTradeCountToday': {'type': 'integer', 'description': '今日新增交易'},
                'reportDate': {'type': 'string', 'format': 'date', 'description': '统计日期'},
            },
        },
    }

    TABLE_TO_ENTITY = {
        'users': 'User', 'roles': 'Role', 'permissions': 'Permission',
        'role_permissions': 'RolePermission', 'user_roles': 'UserRole',
        'collections': 'Collection', 'collection_categories': 'CollectionCategory',
        'collection_images': 'CollectionImage',
        'exchange_requests': 'ExchangeRequest', 'exchange_request_items': 'ExchangeRequestItem',
        'trade_orders': 'TradeOrder', 'trade_reviews': 'TradeReview',
        'credit_records': 'CreditRecord',
        'posts': 'Post', 'comments': 'Comment', 'dynamics': 'Dynamic',
        'post_favorites': 'PostFavorite', 'user_follows': 'UserFollow',
        'reports': 'Report',
        'articles': 'Article', 'article_categories': 'ArticleCategory',
        'announcements': 'Announcement',
        'classification_labels': 'ClassificationLabel',
        'system_configs': 'SystemConfig', 'operation_logs': 'OperationLog',
    }

    ENTITY_TO_TABLE = {v: k for k, v in TABLE_TO_ENTITY.items()}
    SYSTEM_FIELDS = {'id', 'created_at', 'updated_at', 'createdAt', 'updatedAt'}

    def __init__(self, sql_schema: Dict[str, Dict]):
        self.sql_schema = sql_schema

    def derive(self, schema_name: str) -> Optional[Dict]:
        if schema_name in self.SPECIAL_SCHEMAS:
            return self.SPECIAL_SCHEMAS[schema_name].copy()
        if schema_name.endswith('Page'):
            return self._derive_page(schema_name)
        if schema_name.endswith('DTO'):
            return self._derive_dto(schema_name)
        # 处理多种 Request 变体：XxxRequest / XxxCreateRequest / XxxUpdateRequest / XxxCreate
        if schema_name.endswith('CreateRequest'):
            return self._derive_request(schema_name, suffix_len=13)
        if schema_name.endswith('UpdateRequest'):
            return self._derive_request(schema_name, suffix_len=13)
        if schema_name.endswith('Request'):
            return self._derive_request(schema_name, suffix_len=7)
        if schema_name.endswith('Create'):
            return self._derive_request(schema_name, suffix_len=6)
        return self._derive_dto(schema_name + 'DTO') if self._find_table(schema_name) else None

    def _find_table(self, entity_name: str) -> Optional[str]:
        table = self.ENTITY_TO_TABLE.get(entity_name)
        if table and table in self.sql_schema:
            return table
        snake = re.sub(r'(?<!^)(?=[A-Z])', '_', entity_name).lower()
        candidates = [snake, snake + 's', snake + 'es', snake.rstrip('s')]
        for c in candidates:
            if c in self.sql_schema:
                return c
        for table_name in self.sql_schema:
            if snake in table_name or table_name.replace('_', '') == snake.replace('_', ''):
                return table_name
        return None

    def _derive_dto(self, schema_name: str) -> Optional[Dict]:
        entity_name = schema_name[:-3]
        table_name = self._find_table(entity_name)
        if not table_name:
            return None
        table = self.sql_schema[table_name]
        properties = {}
        required = []
        for col in table['columns']:
            prop_name = self._to_camel_case(col['name'])
            prop = {
                'type': col['openapi_type'],
                'description': col['comment'] or f"{col['name']} 字段",
            }
            if col['format']:
                prop['format'] = col['format']
            properties[prop_name] = prop
            if not col['nullable'] and not col['is_auto_increment']:
                required.append(prop_name)
        return {'type': 'object', 'properties': properties, 'required': required}

    def _derive_request(self, schema_name: str, suffix_len: int = 7) -> Optional[Dict]:
        entity_name = schema_name[:-suffix_len]
        table_name = self._find_table(entity_name)
        if not table_name:
            return None
        table = self.sql_schema[table_name]
        properties = {}
        required = []
        for col in table['columns']:
            prop_name = self._to_camel_case(col['name'])
            if prop_name in self.SYSTEM_FIELDS or col['name'] in self.SYSTEM_FIELDS:
                continue
            prop = {
                'type': col['openapi_type'],
                'description': col['comment'] or f"{col['name']} 字段",
            }
            if col['format']:
                prop['format'] = col['format']
            properties[prop_name] = prop
            if not col['nullable']:
                required.append(prop_name)
        return {'type': 'object', 'properties': properties, 'required': required}

    def _derive_page(self, schema_name: str) -> Optional[Dict]:
        entity_name = schema_name[:-4]
        dto_name = entity_name + 'DTO'
        dto = self.derive(dto_name)
        if dto is None:
            return None
        return {
            'type': 'object',
            'properties': {
                'list': {'type': 'array', 'items': {'$ref': f'#/components/schemas/{dto_name}'}, 'description': f'{entity_name} 列表'},
                'total': {'type': 'integer', 'description': '总记录数'},
                'page': {'type': 'integer', 'description': '当前页码'},
                'size': {'type': 'integer', 'description': '每页大小'},
                'pages': {'type': 'integer', 'description': '总页数'},
            },
            'required': ['list', 'total', 'page', 'size'],
        }

    @staticmethod
    def _to_camel_case(snake_str: str) -> str:
        parts = snake_str.split('_')
        return parts[0] + ''.join(word.capitalize() for word in parts[1:])


class APIRepair:
    """API YAML 修复器"""

    def __init__(self, api_yaml: str, db_schema_sql: str):
        self.api_yaml = api_yaml
        self.db_schema_sql = db_schema_sql
        self.parser = SQLSchemaParser()
        self.sql_schema = self.parser.parse(db_schema_sql)

    def repair(self) -> Tuple[str, Dict]:
        report = {
            'yaml_syntax_fixed': False,
            'missing_schemas': [],
            'added_schemas': [],
            'errors': [],
        }
        yaml_text = self.api_yaml

        yaml_text = self._fix_yaml_truncation(yaml_text, report)
        refs = self._extract_refs(yaml_text)
        defined = self._extract_defined_schemas(yaml_text)
        missing = refs - defined
        missing = {m for m in missing if not m.startswith('bearer')}
        report['missing_schemas'] = sorted(missing)

        if missing:
            derivator = DTODerivator(self.sql_schema)
            new_schemas = []
            for name in sorted(missing):
                schema = derivator.derive(name)
                if schema:
                    yaml_snippet = self._schema_to_yaml(name, schema)
                    new_schemas.append(yaml_snippet)
                    report['added_schemas'].append(name)
                else:
                    report['errors'].append(f'无法推导 schema: {name}')
            if new_schemas:
                yaml_text = self._inject_schemas(yaml_text, new_schemas)

        return yaml_text, report

    def _fix_yaml_truncation(self, yaml_text: str, report: Dict) -> str:
        lines = yaml_text.split('\n')
        if not lines:
            return yaml_text
        last_line = lines[-1].rstrip()
        if re.match(r'^\s+\w+$', last_line) and ':' not in last_line:
            lines[-1] = last_line + ":\n          type: string"
            report['yaml_syntax_fixed'] = True
        if lines[-1].strip():
            lines.append('')
        return '\n'.join(lines)

    def _extract_refs(self, yaml_text: str) -> Set[str]:
        refs = set()
        for match in re.finditer(r"\$ref:\s*['\"]?#/components/schemas/(\w+)['\"]?", yaml_text):
            refs.add(match.group(1))
        return refs

    def _extract_defined_schemas(self, yaml_text: str) -> Set[str]:
        defined = set()
        in_schemas = False
        schemas_indent = None
        for line in yaml_text.split('\n'):
            stripped = line.rstrip()
            if stripped == 'schemas:':
                in_schemas = True
                schemas_indent = len(line) - len(line.lstrip())
                continue
            if in_schemas:
                if not stripped:
                    continue
                curr_indent = len(line) - len(line.lstrip())
                if stripped and curr_indent <= schemas_indent:
                    break
                match = re.match(r'^(\s+)([A-Z]\w+):\s*$', stripped)
                if match:
                    defined.add(match.group(2))
        return defined

    def _schema_to_yaml(self, name: str, schema: Dict, indent: int = 6) -> str:
        prefix = ' ' * indent
        lines = [f"{prefix}{name}:", f"{prefix}  type: {schema.get('type', 'object')}"]
        if 'properties' in schema:
            lines.append(f"{prefix}  properties:")
            for prop_name, prop_def in schema['properties'].items():
                lines.append(f"{prefix}    {prop_name}:")
                if isinstance(prop_def, dict):
                    if '$ref' in prop_def:
                        lines.append(f"{prefix}      $ref: '{prop_def['$ref']}'")
                    else:
                        for k, v in prop_def.items():
                            if k == 'enum' and isinstance(v, list):
                                lines.append(f"{prefix}      {k}: {v}")
                            else:
                                lines.append(f"{prefix}      {k}: {v}")
        if 'required' in schema and schema['required']:
            lines.append(f"{prefix}  required: {schema['required']}")
        return '\n'.join(lines)

    def _inject_schemas(self, yaml_text: str, new_schemas: List[str]) -> str:
        lines = yaml_text.split('\n')
        schemas_line_idx = -1
        for i, line in enumerate(lines):
            if line.rstrip() == 'schemas:':
                schemas_line_idx = i
                break
        if schemas_line_idx == -1:
            if 'components:' not in yaml_text:
                yaml_text += "\ncomponents:\n  schemas:\n"
            else:
                yaml_text += "\n  schemas:\n"
            yaml_text += '\n'.join(new_schemas)
            return yaml_text

        schemas_indent = len(lines[schemas_line_idx]) - len(lines[schemas_line_idx].lstrip())
        insert_idx = len(lines)
        for i in range(schemas_line_idx + 1, len(lines)):
            line = lines[i]
            if not line.strip():
                continue
            curr_indent = len(line) - len(line.lstrip())
            if curr_indent <= schemas_indent:
                insert_idx = i
                break

        lines.insert(insert_idx, '\n'.join(new_schemas))
        return '\n'.join(lines)


def repair_api_yaml(api_yaml: str, db_schema_sql: str) -> Tuple[str, Dict]:
    repair = APIRepair(api_yaml, db_schema_sql)
    return repair.repair()
