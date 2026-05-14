from tools.api_repair import repair_api_yaml

with open('workspace/blindbox_community_platform/api.yaml', 'r', encoding='utf-8') as f:
    api = f.read()
with open('workspace/blindbox_community_platform/schema.sql', 'r', encoding='utf-8') as f:
    sql = f.read()

fixed, report = repair_api_yaml(api, sql)
with open('workspace/blindbox_community_platform/api_fixed.yaml', 'w', encoding='utf-8') as f:
    f.write(fixed)

print(f'Fixed: {len(report["added_schemas"])} schemas added, {len(report["errors"])} errors')
