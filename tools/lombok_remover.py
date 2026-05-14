"""
Lombok 后处理工具
将 @Data、@NoArgsConstructor、@AllArgsConstructor 转为显式代码
解决旧版 Maven 与 JDK 21 的 Lombok 注解处理器兼容性问题
"""
import os
import re
from pathlib import Path
from loguru import logger


def _to_camel(name: str) -> str:
    """转为驼峰命名"""
    return name[0].upper() + name[1:]


def _generate_getter(field_type: str, field_name: str) -> str:
    """生成 getter 方法"""
    if field_type == "boolean":
        prefix = "is"
    else:
        prefix = "get"
    return f"""    public {field_type} {prefix}{_to_camel(field_name)}() {{
        return {field_name};
    }}"""


def _generate_setter(field_type: str, field_name: str) -> str:
    """生成 setter 方法"""
    return f"""    public void set{_to_camel(field_name)}({field_type} {field_name}) {{
        this.{field_name} = {field_name};
    }}"""


def _generate_no_args_constructor(class_name: str) -> str:
    """生成无参构造"""
    return f"""    public {class_name}() {{
    }}"""


def _generate_all_args_constructor(fields: list, class_name: str) -> str:
    """生成全参构造"""
    params = ", ".join([f"{t} {n}" for t, n in fields])
    assignments = "\n".join([f"        this.{n} = {n};" for _, n in fields])
    return f"""    public {class_name}({params}) {{
{assignments}
    }}"""


def _generate_required_args_constructor(fields: list, class_name: str) -> str:
    """生成 @RequiredArgsConstructor 对应的构造函数（基于 final 字段）"""
    params = ", ".join([f"{t} {n}" for t, n in fields])
    assignments = "\n".join([f"        this.{n} = {n};" for _, n in fields])
    return f"""    public {class_name}({params}) {{
{assignments}
    }}"""


def _generate_equals(fields: list, class_name: str, call_super: bool = False) -> str:
    """生成 equals() 方法"""
    checks = ["if (this == o) return true;",
              "if (o == null || getClass() != o.getClass()) return false;"]
    if call_super:
        checks.append("if (!super.equals(o)) return false;")
    
    obj_cast = f"{class_name} that = ({class_name}) o;"
    
    primitive_types = {"int", "long", "float", "double", "boolean", "byte", "short", "char"}
    float_types = {"float", "Float"}
    double_types = {"double", "Double"}
    
    comparisons = []
    for field_type, field_name in fields:
        if field_type in float_types:
            comparisons.append(f"if (Float.compare(that.{field_name}, {field_name}) != 0) return false;")
        elif field_type in double_types:
            comparisons.append(f"if (Double.compare(that.{field_name}, {field_name}) != 0) return false;")
        elif field_type in primitive_types:
            comparisons.append(f"if ({field_name} != that.{field_name}) return false;")
        else:
            comparisons.append(f"if (!java.util.Objects.equals({field_name}, that.{field_name})) return false;")
    
    all_lines = ["        " + line for line in checks + [obj_cast] + comparisons + ["return true;"]]
    body = "\n".join(all_lines)
    return f"""    @Override
    public boolean equals(Object o) {{
{body}
    }}"""


def _generate_hashcode(fields: list, call_super: bool = False) -> str:
    """生成 hashCode() 方法——统一使用 Objects.hash 让 Java 自动处理装箱"""
    args = []
    if call_super:
        args.append("super.hashCode()")
    for _, field_name in fields:
        args.append(field_name)
    
    if len(args) == 0:
        return """    @Override
    public int hashCode() {
        return 0;
    }"""
    
    args_str = ", ".join(args)
    return f"""    @Override
    public int hashCode() {{
        return java.util.Objects.hash({args_str});
    }}"""


def _extract_fields(content: str) -> list:
    """提取类中的字段（类型, 名称）"""
    fields = []
    # 匹配 private Type fieldName; 或 private Type fieldName = ...;
    pattern = re.compile(r'^\s+private\s+(\S+(?:<[^>]+>)?)\s+(\w+)(?:\s*=\s*[^;]+)?;', re.MULTILINE)
    for match in pattern.finditer(content):
        field_type = match.group(1)
        field_name = match.group(2)
        # 排除 static final 常量
        start = match.start()
        line_start = content.rfind('\n', 0, start) + 1
        line = content[line_start:start]
        if 'static' in line and 'final' in line:
            continue
        fields.append((field_type, field_name))
    return fields


def _extract_class_name(content: str) -> str:
    """提取类名"""
    match = re.search(r'public\s+class\s+(\w+)', content)
    return match.group(1) if match else "Unknown"


def remove_lombok_from_file(filepath: str) -> bool:
    """
    处理单个 Java 文件，将 Lombok 注解转为显式代码
    :return: 是否修改了文件
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 检测所有需要处理的 Lombok 注解
    has_lombok = any(ann in content for ann in [
        '@Data', '@Builder', '@Getter', '@Setter',
        '@NoArgsConstructor', '@AllArgsConstructor',
        '@RequiredArgsConstructor', '@EqualsAndHashCode',
        '@ToString', '@Slf4j', '@Log4j2',
    ])
    if not has_lombok:
        return False

    original = content
    class_name = _extract_class_name(content)
    fields = _extract_fields(content)

    # 生成方法
    methods = []

    # 无参构造
    if '@NoArgsConstructor' in content:
        methods.append(_generate_no_args_constructor(class_name))

    # 全参构造
    if '@AllArgsConstructor' in content:
        methods.append(_generate_all_args_constructor(fields, class_name))

    # getter/setter（@Data 或单独的 @Getter/@Setter）
    need_getter = '@Data' in content or '@Getter' in content
    need_setter = '@Data' in content or '@Setter' in content
    if need_getter or need_setter:
        for field_type, field_name in fields:
            if need_getter:
                methods.append(_generate_getter(field_type, field_name))
            if need_setter:
                methods.append(_generate_setter(field_type, field_name))

    # @Builder 太复杂，直接移除注解（不做 builder 模式转换）
    # 依赖 @Builder 的代码在编译时会报错，需要 Fix Agent 或人工处理

    # ===== 处理 @RequiredArgsConstructor =====
    # 必须在删除 final 之前提取 final 字段，生成构造函数
    if '@RequiredArgsConstructor' in content:
        final_fields = []
        for match in re.finditer(r'^\s+private\s+final\s+(\S+(?:<[^>]+>)?)\s+(\w+)(?:\s*=\s*[^;]+)?;', content, re.MULTILINE):
            final_fields.append((match.group(1), match.group(2)))
        if final_fields:
            ctor = _generate_required_args_constructor(final_fields, class_name)
            methods.append(ctor)

    # ===== 处理 @EqualsAndHashCode =====
    eq_match = re.search(r'@EqualsAndHashCode\s*\(\s*(?:[^)]*callSuper\s*=\s*(true|True|TRUE)[^)]*)?\s*\)', content)
    if '@EqualsAndHashCode' in content:
        call_super = bool(eq_match and eq_match.group(1))
        methods.append(_generate_equals(fields, class_name, call_super))
        methods.append(_generate_hashcode(fields, call_super))

    if not methods and '@Builder' not in content:
        return False

    # 删除 Lombok import
    content = re.sub(r'import\s+lombok\.\w+;\n', '', content)

    # 删除 Lombok 注解（整行）—— @EqualsAndHashCode 可能带参数，用更灵活的正则
    content = re.sub(r'^\s*@Data\s*\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\s*@NoArgsConstructor\s*\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\s*@AllArgsConstructor\s*\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\s*@RequiredArgsConstructor\s*\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\s*@Getter\s*\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\s*@Setter\s*\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\s*@Builder\s*\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\s*@EqualsAndHashCode\s*(?:\([^)]*\))?\s*\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\s*@ToString\s*\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\s*@Slf4j\s*\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\s*@Log4j2\s*\n', '', content, flags=re.MULTILINE)
    # 将 private final Type field; 改为 private Type field;
    content = re.sub(r'private\s+final\s+', 'private ', content)

    # 在类最后一个 } 之前插入方法
    last_brace = content.rfind('}')
    if last_brace > 0:
        methods_str = '\n\n'.join(methods)
        content = content[:last_brace] + '\n\n' + methods_str + '\n' + content[last_brace:]

    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.info(f"[LombokRemover] 已处理: {filepath}")
        return True

    return False


def remove_lombok_from_project(project_dir: str) -> int:
    """
    处理项目中的所有 Java 文件
    :return: 修改的文件数
    """
    src_dir = Path(project_dir) / "src" / "main" / "java"
    if not src_dir.exists():
        return 0

    count = 0
    for filepath in src_dir.rglob("*.java"):
        if remove_lombok_from_file(str(filepath)):
            count += 1

    logger.info(f"[LombokRemover] 共处理 {count} 个文件")
    return count


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        remove_lombok_from_project(sys.argv[1])
    else:
        print("Usage: python lombok_remover.py <project_dir>")
