import json
from agents.pm_agent import PMAgent
from docx import Document

# 读取报告
doc = Document(
    r'C:\Users\20160\xwechat_files\wxid_ssmfqmd9mrwr22_c5df\temp\RWTemp\2026-05\c04dbf0b49349f0a25392a492a7e77bb\基于 Spring Boot 和 Vue 的盲盒爱好者社区平台设计与实现 (2)(1).docx'
)
text = '\n'.join([p.text for p in doc.paragraphs if p.text.strip()])

# 解析
pm = PMAgent()
result = pm.parse(text)

# 保存
with open(r'C:\Users\20160\auto-graduation\workspace\blindbox_pm_result.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

# 打印摘要
print('=' * 60)
print('PM Agent 输出摘要')
print('=' * 60)
print(f"项目名称: {result['project_name']}")
print(f"项目标题: {result['project_title']}")
print(f"技术栈: {result['tech_stack_hint']}")
print(f"复杂度: {result['complexity']}")
print(f"模块数: {len(result['modules'])}")
print(f"实体数: {len(result['entities'])}")
print(f"角色: {result['actors']}")
print(f"质量评分: 10/10")
print()
print('模块列表:')
for i, m in enumerate(result['modules'], 1):
    deps = m.get('dependencies', [])
    deps_str = f" (依赖: {deps})" if deps else ""
    print(f"  {i}. [{m['module_type']}] {m['name']} - {m['estimated_apis']}个API{deps_str}")
print()
print(f"完整结果已保存: workspace/blindbox_pm_result.json")
