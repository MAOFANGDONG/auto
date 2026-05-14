import re
from collections import defaultdict

with open(r'C:\Users\20160\auto-graduation\workspace\blindbox_community_platform\api.yaml', 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')
current_path = ''
endpoints = []

for i, line in enumerate(lines):
    stripped = line.strip()
    
    if stripped.startswith('/api/') and ':' in stripped and not stripped.startswith('/api/' + ' '):
        current_path = stripped.rstrip(':')
    
    if current_path and stripped in ('get:', 'post:', 'put:', 'delete:', 'patch:'):
        method = stripped.rstrip(':').upper()
        
        summary = ''
        tags = []
        for j in range(i+1, min(i+15, len(lines))):
            jl = lines[j].strip()
            if jl.startswith('summary:'):
                summary = jl.replace('summary:', '').strip().strip('"').strip("'")
            if jl.startswith('tags:'):
                for k in range(j+1, min(j+5, len(lines))):
                    kl = lines[k].strip()
                    if kl.startswith('- '):
                        tag_val = kl.replace('- ', '').strip().strip('"').strip("'")
                        tags.append(tag_val)
            if jl.startswith('operationId:'):
                break
        
        tag = tags[0] if tags else '未分类'
        endpoints.append((tag, method, current_path, summary))

by_tag = defaultdict(list)
for tag, method, path, summary in endpoints:
    by_tag[tag].append((method, path, summary))

for tag in sorted(by_tag.keys()):
    print(f'\n【{tag}】')
    print('-' * 90)
    for method, path, summary in by_tag[tag]:
        print(f'  {method:6} {path:55} {summary}')

print(f'\n\n总计: {len(endpoints)} 个接口')
