"""
运行图书借阅管理系统完整流程
"""
from main import run_pipeline

report = """
基于SpringBoot的图书借阅管理系统设计与实现

一、项目背景
随着高校图书馆藏书量不断增加，传统的人工管理方式效率低下。本系统旨在实现图书馆的信息化管理，提高借阅效率。

二、系统功能模块
1. 用户管理：读者注册登录、个人信息维护、管理员账号管理
2. 图书管理：图书录入、编辑、分类管理、库存查询
3. 借阅管理：借书申请、还书登记、借阅记录查询、逾期提醒
4. 预约管理：图书预约、取消预约、预约到期通知
5. 公告管理：管理员发布公告、读者查看公告

三、技术选型
后端：SpringBoot 3.x + Spring Data JPA + MySQL
前端：Vue3 + Element Plus
移动端：微信小程序

四、数据库要求
支持图书信息、用户信息、借阅记录、预约记录的数据持久化
"""

print("[Auto-Graduation] 启动图书借阅管理系统生成流程")
print("=" * 60)
final_state = run_pipeline(report, thread_id="library_001")
print(f"\n最终状态: {final_state['current_stage']}")
