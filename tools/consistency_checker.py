"""
跨文件一致性检查器
基于 JavaIndex 执行多维度一致性校验
"""
import re
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from tools.java_indexer import JavaIndex, ClassInfo, MethodInfo


@dataclass
class Issue:
    severity: str  # "error" | "warning"
    issue_type: str
    message: str
    file_path: str
    line_number: int = 0
    related_file: Optional[str] = None
    suggestion: Optional[str] = None


class ConsistencyChecker:
    """基于 JavaIndex 的一致性检查器"""

    # Spring Data JPA 有效方法前缀
    VALID_REPO_PREFIXES = ('findBy', 'existsBy', 'countBy', 'deleteBy', 'findAllBy',
                           'findFirstBy', 'findTopBy', 'findDistinctBy')

    def __init__(self, index: JavaIndex):
        self.index = index
        self.issues: List[Issue] = []

    def check(self) -> List[Issue]:
        """执行所有检查"""
        self.issues = []
        self._check_interface_impl()
        self._check_enum_usage()
        self._check_repository_methods()
        self._check_field_references()
        self._check_cross_service_calls()
        return self.issues

    def _check_interface_impl(self):
        """检查 ServiceImpl 是否完整实现了接口"""
        for fqn, cls in self.index.classes.items():
            if cls.class_type != 'class':
                continue
            # Find implemented interfaces
            for iface_fqn in cls.interfaces:
                iface = self.index.get_class(iface_fqn)
                if not iface or iface.class_type != 'interface':
                    continue
                # Check each interface method
                for imethod in iface.methods:
                    if imethod.is_static:
                        continue
                    matched = self._find_matching_method(cls, imethod)
                    if not matched:
                        self.issues.append(Issue(
                            severity="error",
                            issue_type="missing_method_impl",
                            message=f"{cls.name} 未实现接口 {iface.name} 的方法: {self._method_sig(imethod)}",
                            file_path=cls.file_path,
                            related_file=iface.file_path,
                            suggestion=f"在 {cls.name} 中添加方法实现: {self._method_sig(imethod)}",
                        ))

    def _find_matching_method(self, cls: ClassInfo, target: MethodInfo) -> bool:
        """在类中查找匹配的方法（支持继承）"""
        for m in cls.methods:
            if m.name == target.name and len(m.params) == len(target.params):
                return True
        # Check super class
        if cls.super_class:
            super_cls = self.index.get_class(cls.super_class)
            if super_cls:
                return self._find_matching_method(super_cls, target)
        return False

    def _check_enum_usage(self):
        """检查枚举类型使用是否正确"""
        for fqn, cls in self.index.classes.items():
            # Only check implementation files
            if 'impl' not in cls.file_path and 'controller' not in cls.file_path.lower():
                continue

            try:
                with open(cls.file_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
            except Exception:
                continue

            # Find all enum values referenced
            for line_no, line in enumerate(content.split('\n'), 1):
                # Pattern: SomeEnum.VALUE.name() used as setter argument
                matches = re.finditer(r'(\w+)\.(\w+)\.name\(\)', line)
                for m in matches:
                    enum_type = m.group(1)
                    # Check if the result is assigned to an enum-typed field
                    if self._is_assigned_to_enum_field(line, enum_type, content, line_no):
                        self.issues.append(Issue(
                            severity="error",
                            issue_type="enum_type_mismatch",
                            message=f"将枚举的 .name() 结果（String）赋值给枚举类型字段",
                            file_path=cls.file_path,
                            line_number=line_no,
                            suggestion=f"去掉 .name()，直接使用 {enum_type}.{m.group(2)}",
                        ))

                # Pattern: String literal assigned to enum field
                str_assigns = re.finditer(r'(\w+)\.set(\w+)\s*\(\s*["\']', line)
                for m in str_assigns:
                    obj_name = m.group(1)
                    field_name = m.group(2)[0].lower() + m.group(2)[1:]
                    field_type = self._infer_object_type(obj_name, cls, content)
                    if field_type:
                        actual_type = self.index.get_field_type(field_type, field_name)
                        if actual_type and actual_type in self.index.classes:
                            target_cls = self.index.classes[actual_type]
                            if target_cls.class_type == 'enum':
                                self.issues.append(Issue(
                                    severity="error",
                                    issue_type="enum_type_mismatch",
                                    message=f"将 String 直接赋值给枚举类型字段 {field_name}",
                                    file_path=cls.file_path,
                                    line_number=line_no,
                                    suggestion=f"使用 {target_cls.name}.valueOf(...) 转换",
                                ))

    def _is_assigned_to_enum_field(self, line: str, enum_type: str, content: str, line_no: int) -> bool:
        """检查当前行是否将 .name() 结果赋值给枚举类型的 setter"""
        # Look for pattern: obj.setXxx(Enum.VALUE.name())
        m = re.search(r'(\w+)\.set(\w+)\s*\(.*' + re.escape(enum_type) + r'\.\w+\.name\(\)', line)
        if m:
            obj_name = m.group(1)
            field_name = m.group(2)[0].lower() + m.group(2)[1:]
            # Try to infer object type
            for fqn, cls in self.index.classes.items():
                if cls.file_path and ('impl' in cls.file_path or 'controller' in cls.file_path.lower()):
                    field_type = self.index.get_field_type(fqn, field_name)
                    if field_type and field_type in self.index.classes:
                        target = self.index.classes[field_type]
                        if target.class_type == 'enum':
                            return True
        return False

    def _check_repository_methods(self):
        """检查 Repository 方法命名是否合法，以及调用是否存在"""
        for fqn, cls in self.index.classes.items():
            if 'Repository' not in cls.name or cls.class_type != 'interface':
                continue
            for m in cls.methods:
                if not m.annotations and not m.name.startswith(self.VALID_REPO_PREFIXES):
                    # Allow standard JPA methods
                    if m.name in ('save', 'saveAll', 'findById', 'findAll', 'existsById',
                                  'count', 'deleteById', 'delete', 'deleteAll', 'getReferenceById',
                                  'findOne', 'findAllById'):
                        continue
                    self.issues.append(Issue(
                        severity="warning",
                        issue_type="invalid_repo_method",
                        message=f"Repository {cls.name} 的方法 {m.name} 可能不是有效的 Spring Data JPA 查询方法",
                        file_path=cls.file_path,
                        suggestion="添加 @Query 注解，或遵循 findBy/existsBy/countBy/deleteBy 命名规范",
                    ))

    def _check_field_references(self):
        """检查 getter/setter 调用是否合法"""
        for fqn, cls in self.index.classes.items():
            if 'impl' not in cls.file_path and 'controller' not in cls.file_path.lower():
                continue

            try:
                with open(cls.file_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
            except Exception:
                continue

            # Find all getter/setter calls: obj.getXxx() or obj.setXxx(...)
            for line_no, line in enumerate(content.split('\n'), 1):
                # Getter calls
                for m in re.finditer(r'(\w+)\.(get|is)(\w+)\s*\(\s*\)', line):
                    obj_name = m.group(1)
                    verb = m.group(2)
                    prop = m.group(3)
                    field_name = prop[0].lower() + prop[1:]
                    self._validate_field_ref(obj_name, field_name, cls, content, line_no, line, f"getter {verb}{prop}")

                # Setter calls
                for m in re.finditer(r'(\w+)\.(set)(\w+)\s*\(', line):
                    obj_name = m.group(1)
                    prop = m.group(3)
                    field_name = prop[0].lower() + prop[1:]
                    self._validate_field_ref(obj_name, field_name, cls, content, line_no, line, f"setter set{prop}")

    def _validate_field_ref(self, obj_name: str, field_name: str, cls: ClassInfo, content: str, line_no: int, line: str, ref_desc: str):
        """验证字段引用是否合法"""
        obj_type = self._infer_object_type(obj_name, cls, content)
        if not obj_type:
            return

        target_cls = self.index.get_class(obj_type)
        if not target_cls:
            return

        # Check if field exists
        has_field = self.index.has_field(obj_type, field_name)
        if not has_field:
            self.issues.append(Issue(
                severity="error",
                issue_type="unresolved_field",
                message=f"{target_cls.name} 中没有字段 '{field_name}'（通过 {ref_desc}() 引用）",
                file_path=cls.file_path,
                line_number=line_no,
                related_file=target_cls.file_path,
                suggestion=f"检查 {target_cls.name} 的实际字段名",
            ))

    def _check_cross_service_calls(self):
        """检查 Controller/ServiceImpl 中对其他 Service 的方法调用是否合法"""
        for fqn, cls in self.index.classes.items():
            if 'impl' not in cls.file_path and 'controller' not in cls.file_path.lower():
                continue

            try:
                with open(cls.file_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
            except Exception:
                continue

            # Find all method calls on injected fields (likely Services/Repositories)
            for line_no, line in enumerate(content.split('\n'), 1):
                # Pattern: objName.methodName(args)
                for m in re.finditer(r'(\w+)\.(\w+)\s*\(([^)]*)\)', line):
                    obj_name = m.group(1)
                    method_name = m.group(2)
                    # Skip common Java methods
                    if method_name in ('toString', 'equals', 'hashCode', 'getClass',
                                       'stream', 'map', 'filter', 'collect', 'orElseThrow',
                                       'get', 'set', 'add', 'remove', 'size', 'isEmpty'):
                        continue
                    obj_type = self._infer_object_type(obj_name, cls, content)
                    if not obj_type:
                        continue
                    target_cls = self.index.get_class(obj_type)
                    if not target_cls:
                        continue
                    # Only check interfaces (Services) and Repositories
                    if target_cls.class_type != 'interface':
                        continue
                    # Count args
                    args_str = m.group(3).strip()
                    arg_count = len([a for a in args_str.split(',') if a.strip()]) if args_str else 0
                    if not self.index.has_method(obj_type, method_name, arg_count):
                        # Try with -1 (any param count)
                        if not self.index.has_method(obj_type, method_name, -1):
                            self.issues.append(Issue(
                                severity="error",
                                issue_type="unresolved_method",
                                message=f"{target_cls.name} 中没有方法 {method_name}({arg_count}个参数)",
                                file_path=cls.file_path,
                                line_number=line_no,
                                related_file=target_cls.file_path,
                                suggestion=f"在 {target_cls.name} 中添加方法声明，或检查方法名/参数",
                            ))

    def _infer_object_type(self, obj_name: str, cls: ClassInfo, content: str) -> Optional[str]:
        """推断对象的类型（简化版）"""
        # Check constructor-injected fields
        for f in cls.fields:
            if f.name == obj_name:
                return f.field_type

        # Check local declarations in content: Type objName = ...
        decl_pattern = re.compile(r'\b(\S+(?:<[^>]+>)?)\s+' + re.escape(obj_name) + r'\b')
        m = decl_pattern.search(content)
        if m:
            raw_type = m.group(1).strip()
            # Resolve through imports
            return self._resolve_type_from_context(raw_type, cls)

        # Check method parameters (current method scope - simplified)
        return None

    def _resolve_type_from_context(self, raw_type: str, cls: ClassInfo) -> str:
        """根据类的 imports 解析类型"""
        if '.' in raw_type:
            return raw_type
        # Check imports
        for imp in cls.imports:
            if imp.endswith(f'.{raw_type}'):
                return imp
            if imp.endswith('.*'):
                pkg = imp[:-2]
                candidate = f"{pkg}.{raw_type}"
                if candidate in self.index.classes:
                    return candidate
        # Same package
        candidate = f"{cls.package}.{raw_type}"
        if candidate in self.index.classes:
            return candidate
        return raw_type

    @staticmethod
    def _method_sig(m: MethodInfo) -> str:
        params = ", ".join([f"{t} {n}" for t, n in m.params])
        return f"{m.return_type} {m.name}({params})"
