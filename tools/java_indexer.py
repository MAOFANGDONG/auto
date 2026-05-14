"""
Java 文件索引器
基于正则解析所有 Java 文件，建立全局类索引
用于跨文件一致性校验
"""
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from pathlib import Path


@dataclass
class FieldInfo:
    name: str
    field_type: str
    annotations: List[str] = field(default_factory=list)


@dataclass
class MethodInfo:
    name: str
    return_type: str
    params: List[tuple]  # [(type, name), ...]
    annotations: List[str] = field(default_factory=list)
    is_abstract: bool = False
    is_static: bool = False


@dataclass
class ClassInfo:
    name: str
    package: str
    file_path: str
    class_type: str  # "class", "interface", "enum"
    super_class: Optional[str] = None
    interfaces: List[str] = field(default_factory=list)
    fields: List[FieldInfo] = field(default_factory=list)
    methods: List[MethodInfo] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    annotations: List[str] = field(default_factory=list)
    is_abstract: bool = False


class JavaIndex:
    """Java 项目全局索引"""

    def __init__(self):
        # fully_qualified_name -> ClassInfo
        self.classes: Dict[str, ClassInfo] = {}
        # simple_name -> fully_qualified_name (for resolution)
        self.simple_names: Dict[str, str] = {}
        # file_path -> list of class names defined in file
        self.file_classes: Dict[str, List[str]] = {}

    def build(self, project_dir: str) -> "JavaIndex":
        """扫描项目中的所有 Java 文件并建立索引"""
        src_dir = Path(project_dir) / "src" / "main" / "java"
        if not src_dir.exists():
            return self

        for java_file in src_dir.rglob("*.java"):
            self._parse_file(str(java_file))

        # Build simple name index
        for fqn, cls in self.classes.items():
            simple = cls.name.split('.')[-1]
            self.simple_names[simple] = fqn

        return self

    def _parse_file(self, file_path: str):
        """解析单个 Java 文件"""
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception:
            return

        # Remove comments to simplify parsing
        content = self._strip_comments(content)

        # Extract package
        pkg_match = re.search(r'^\s*package\s+([\w.]+)\s*;', content, re.MULTILINE)
        package = pkg_match.group(1) if pkg_match else ""

        # Extract imports
        imports = re.findall(r'^\s*import\s+([\w.*]+)\s*;', content, re.MULTILINE)

        # Find class/interface/enum declarations
        # Match: public [abstract] [class|interface|enum] Name [<T>] [extends X] [implements Y, Z]
        pattern = re.compile(
            r'(?:(public|protected|private)\s+)?'
            r'(abstract\s+)?'
            r'(class|interface|enum)\s+'
            r'(\w+)'
            r'(?:\s*<[^>]+>)?\s*'
            r'(?:extends\s+([\w<>,\s]+))?\s*'
            r'(?:implements\s+([\w<>,\s]+))?\s*\{',
            re.MULTILINE
        )

        classes_in_file = []

        for m in pattern.finditer(content):
            visibility = m.group(1)
            is_abstract = m.group(2) is not None
            class_type = m.group(3)
            name = m.group(4)
            super_class = m.group(5)
            implements = m.group(6)

            # Find class body boundaries
            start = m.end() - 1  # position of '{'
            end = self._find_matching_brace(content, start)
            if end < 0:
                continue
            body = content[start + 1:end]

            cls = ClassInfo(
                name=name,
                package=package,
                file_path=file_path,
                class_type=class_type,
                super_class=self._resolve_type(super_class, package, imports) if super_class else None,
                interfaces=self._resolve_type_list(implements, package, imports) if implements else [],
                imports=imports,
                is_abstract=is_abstract,
            )

            # Extract annotations before declaration
            decl_start = m.start()
            before_decl = content[max(0, decl_start - 500):decl_start]
            cls.annotations = re.findall(r'@(\w+(?:\([^)]*\))?)', before_decl)

            # Parse fields and methods from body
            self._parse_body(body, cls, package, imports)

            fqn = f"{package}.{name}" if package else name
            self.classes[fqn] = cls
            classes_in_file.append(fqn)

        if classes_in_file:
            self.file_classes[file_path] = classes_in_file

    def _strip_comments(self, content: str) -> str:
        """移除注释"""
        # Remove line comments
        content = re.sub(r'//.*$', '', content, flags=re.MULTILINE)
        # Remove block comments (simple, may not handle nested perfectly)
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        return content

    def _find_matching_brace(self, text: str, open_pos: int) -> int:
        """找到匹配的右大括号"""
        depth = 1
        i = open_pos + 1
        in_string = False
        string_char = None
        while i < len(text):
            c = text[i]
            if in_string:
                if c == string_char and text[i - 1] != '\\':
                    in_string = False
                i += 1
                continue
            if c in ('"', "'"):
                in_string = True
                string_char = c
                i += 1
                continue
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return i
            i += 1
        return -1

    def _parse_body(self, body: str, cls: ClassInfo, package: str, imports: List[str]):
        """解析类体中的字段和方法"""
        # Remove inner classes for field/method parsing to avoid confusion
        body = re.sub(r'\b(class|interface|enum)\s+\w+\s*\{', '', body)

        # Remove equals/hashCode/toString methods to avoid parsing local variables as fields
        # Simple heuristic: remove method bodies that start with these method signatures
        for method_name in ('equals', 'hashCode', 'toString'):
            pattern = re.compile(rf'\b(public\s+)?\s*(boolean|int|String)\s+{method_name}\s*\([^)]*\)\s*\{{', re.MULTILINE)
            for mm in pattern.finditer(body):
                start = mm.end() - 1
                end = self._find_matching_brace(body, start)
                if end > 0:
                    body = body[:mm.start()] + body[end + 1:]

        # Parse fields: [annotations] [modifiers] Type name [= init];
        field_pattern = re.compile(
            r'^(\s*)'  # leading whitespace
            r'((?:@\w+(?:\([^)]*\))?\s+)*)'  # annotations
            r'((?:private|public|protected|static|final|transient|volatile)\s+)*'
            r'(\S+(?:<[^>]+>)?)\s+'  # type
            r'(\w+)'  # name
            r'(?:\s*=\s*[^;]+)?'  # optional initializer
            r'\s*;',
            re.MULTILINE
        )

        seen_fields = set()
        for m in field_pattern.finditer(body):
            annots = re.findall(r'@(\w+(?:\([^)]*\))?)', m.group(2) or '')
            field_type = m.group(4).strip()
            field_name = m.group(5)
            # Skip if already seen (avoid duplicates)
            if field_name in seen_fields:
                continue
            seen_fields.add(field_name)
            # Skip common local variable names from method parsing leaks
            if field_name in ('that', 'result', 'true', 'false', 'o', 'obj'):
                continue
            cls.fields.append(FieldInfo(
                name=field_name,
                field_type=self._resolve_type(field_type, package, imports),
                annotations=annots,
            ))

        # Parse methods
        # Match method signatures (including constructors)
        method_pattern = re.compile(
            r'^(\s*)'
            r'((?:@\w+(?:\([^)]*\))?\s+)*)'  # annotations
            r'((?:private|public|protected|static|abstract|final|synchronized)\s+)*'
            r'(\S+(?:<[^>]+>)?)\s+'  # return type (or class name for constructor)
            r'(\w+)'  # method name
            r'\s*\(([^)]*)\)\s*'  # parameters
            r'(?:throws\s+[\w<>,\s]+)?\s*'
            r'(?:\{|;)',
            re.MULTILINE
        )

        for m in method_pattern.finditer(body):
            annots = re.findall(r'@(\w+(?:\([^)]*\))?)', m.group(2) or '')
            modifiers = m.group(3) or ''
            return_type = m.group(4).strip()
            method_name = m.group(5)
            params_str = m.group(6).strip()

            # Skip if it looks like a field declaration (has assignment)
            # or if return_type + method_name doesn't look like a method
            if return_type in ('if', 'while', 'for', 'switch', 'catch', 'return'):
                continue

            is_static = 'static' in modifiers
            is_abstract = 'abstract' in modifiers or cls.class_type == 'interface'

            params = self._parse_params(params_str, package, imports)

            cls.methods.append(MethodInfo(
                name=method_name,
                return_type=self._resolve_type(return_type, package, imports),
                params=params,
                annotations=annots,
                is_abstract=is_abstract,
                is_static=is_static,
            ))

    def _parse_params(self, params_str: str, package: str, imports: List[str]) -> List[tuple]:
        """解析方法参数列表 [(type, name), ...]"""
        params = []
        if not params_str:
            return params
        # Split by comma, but respect generics
        parts = self._split_params(params_str)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            # Remove annotations
            part = re.sub(r'@\w+(?:\([^)]*\))?\s*', '', part).strip()
            # Match: Type name
            m = re.match(r'([\w<>,\s\[\]?]+)\s+(\w+)\s*$', part)
            if m:
                ptype = self._resolve_type(m.group(1).strip(), package, imports)
                pname = m.group(2)
                params.append((ptype, pname))
        return params

    def _split_params(self, params_str: str) -> List[str]:
        """按逗号分割参数，但尊重泛型括号"""
        parts = []
        current = ""
        depth = 0
        for c in params_str:
            if c == '<':
                depth += 1
            elif c == '>':
                depth -= 1
            elif c == ',' and depth == 0:
                parts.append(current)
                current = ""
                continue
            current += c
        if current.strip():
            parts.append(current)
        return parts

    def _resolve_type(self, type_name: str, package: str, imports: List[str]) -> str:
        """将简单类型名解析为全限定名"""
        if not type_name:
            return type_name
        type_name = type_name.strip()

        # Primitive types and void
        if type_name in ('void', 'int', 'long', 'short', 'byte', 'float', 'double', 'boolean', 'char'):
            return type_name

        # Array types
        if type_name.endswith('[]'):
            base = type_name[:-2]
            return self._resolve_type(base, package, imports) + '[]'

        # Generic types - resolve base
        if '<' in type_name:
            base = type_name[:type_name.index('<')].strip()
            resolved_base = self._resolve_type(base, package, imports)
            return resolved_base + type_name[type_name.index('<'):]

        # Fully qualified already
        if '.' in type_name:
            return type_name

        # Check imports
        for imp in imports:
            if imp.endswith(f'.{type_name}'):
                return imp
            if imp.endswith('.*'):
                pkg = imp[:-2]
                candidate = f"{pkg}.{type_name}"
                if candidate in self.classes:
                    return candidate

        # Same package
        candidate = f"{package}.{type_name}"
        if candidate in self.classes:
            return candidate

        # java.lang (implicit import)
        return type_name

    def _resolve_type_list(self, types_str: str, package: str, imports: List[str]) -> List[str]:
        """解析逗号分隔的类型列表"""
        result = []
        for t in self._split_params(types_str):
            t = t.strip()
            if t:
                result.append(self._resolve_type(t, package, imports))
        return result

    def get_class(self, fqn_or_simple: str) -> Optional[ClassInfo]:
        """通过全限定名或简单名获取类信息"""
        if fqn_or_simple in self.classes:
            return self.classes[fqn_or_simple]
        if fqn_or_simple in self.simple_names:
            return self.classes[self.simple_names[fqn_or_simple]]
        return None

    def find_impls_of(self, interface_fqn: str) -> List[ClassInfo]:
        """找到实现了指定接口的所有类"""
        result = []
        for cls in self.classes.values():
            if interface_fqn in cls.interfaces:
                result.append(cls)
        return result

    def has_field(self, cls_fqn: str, field_name: str) -> bool:
        """检查类是否有指定字段（含继承）"""
        cls = self.get_class(cls_fqn)
        if not cls:
            return False
        # Check own fields
        if any(f.name == field_name for f in cls.fields):
            return True
        # Check super class
        if cls.super_class:
            return self.has_field(cls.super_class, field_name)
        return False

    def get_field_type(self, cls_fqn: str, field_name: str) -> Optional[str]:
        """获取字段类型（含继承）"""
        cls = self.get_class(cls_fqn)
        if not cls:
            return None
        for f in cls.fields:
            if f.name == field_name:
                return f.field_type
        if cls.super_class:
            return self.get_field_type(cls.super_class, field_name)
        return None

    def has_method(self, cls_fqn: str, method_name: str, param_count: int = -1) -> bool:
        """检查类是否有指定方法（含继承）"""
        cls = self.get_class(cls_fqn)
        if not cls:
            return False
        for m in cls.methods:
            if m.name == method_name:
                if param_count < 0 or len(m.params) == param_count:
                    return True
        if cls.super_class:
            return self.has_method(cls.super_class, method_name, param_count)
        return False

    def __repr__(self):
        return f"JavaIndex(classes={len(self.classes)}, files={len(self.file_classes)})"
