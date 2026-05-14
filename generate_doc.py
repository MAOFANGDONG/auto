# -*- coding: utf-8 -*-
"""生成项目说明 Word 文档"""
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn


def set_heading_style(run, size=14, bold=True, color=RGBColor(0, 0, 128)):
    font = run.font
    font.size = Pt(size)
    font.bold = bold
    font.color.rgb = color
    run.font.name = '微软雅黑'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')


def set_body_style(run, size=10.5):
    font = run.font
    font.size = Pt(size)
    run.font.name = '微软雅黑'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')


def add_bold_paragraph(doc, title, desc):
    p = doc.add_paragraph()
    r = p.add_run(title)
    r.font.bold = True
    set_body_style(r)
    r = p.add_run(' — ' + desc)
    set_body_style(r)


def main():
    doc = Document()

    # ========== 标题 ==========
    title = doc.add_heading('', level=0)
    title_run = title.add_run('auto-graduation 项目文档')
    title_run.font.size = Pt(22)
    title_run.font.bold = True
    title_run.font.color.rgb = RGBColor(0, 51, 102)
    title_run.font.name = '微软雅黑'
    title_run._element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    subtitle = doc.add_paragraph()
    subtitle_run = subtitle.add_run('多 Agent 自动代码生成系统 — 框架流程与文件作用说明')
    subtitle_run.font.size = Pt(12)
    subtitle_run.font.color.rgb = RGBColor(100, 100, 100)
    subtitle_run.font.name = '微软雅黑'
    subtitle_run._element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph()
    info = doc.add_paragraph()
    info_run = info.add_run('生成时间：2026-05-12\n项目路径：C:\\Users\\20160\\auto-graduation')
    set_body_style(info_run)
    info.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_page_break()

    # ========== 目录 ==========
    h = doc.add_heading('', level=1)
    set_heading_style(h.add_run('目录'), size=16)

    toc_items = [
        '1. 项目概述',
        '2. 系统架构与核心流程',
        '3. 文件清单与作用说明',
        '   3.1 根目录文件',
        '   3.2 agents/ — Agent 实现层',
        '   3.3 prompts/ — Prompt 模板层',
        '   3.4 tools/ — 工具层',
        '   3.5 templates/ — 项目模板层',
        '   3.6 skills/ — 技能规范',
        '   3.7 test/ — 测试',
        '   3.8 workspace/ — 输出目录',
        '4. Agent 协作流程详解',
        '5. 关键设计决策',
    ]
    for item in toc_items:
        style = 'List Number' if not item.startswith('   ') else 'List Bullet'
        p = doc.add_paragraph(item, style=style)
        for run in p.runs:
            set_body_style(run)

    doc.add_page_break()

    # ========== 1. 项目概述 ==========
    h = doc.add_heading('', level=1)
    set_heading_style(h.add_run('1. 项目概述'), size=16)

    p = doc.add_paragraph()
    t = p.add_run('auto-graduation 是一个基于 LangGraph 的多 Agent 自动代码生成系统。用户输入一份中文开题报告，系统通过流水线式的多 Agent 协作，自动生成完整的可编译、可运行的毕业设计项目代码。')
    set_body_style(t)

    p = doc.add_paragraph()
    t = p.add_run('支持技术栈：Java + SpringBoot + Vue3 + 微信小程序，以及 Python + FastAPI + Vue3 + 微信小程序。')
    set_body_style(t)

    p = doc.add_paragraph()
    t = p.add_run('核心 LLM：DeepSeek V4 Pro（通过 LangChain OpenAI 适配器调用）。')
    set_body_style(t)

    doc.add_paragraph()
    p = doc.add_paragraph()
    set_heading_style(p.add_run('项目统计'), size=12)
    table = doc.add_table(rows=1, cols=2)
    table.style = 'Light Grid Accent 1'
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = '类别'
    hdr_cells[1].text = '数量'
    stats = [
        ('Python 源文件', '16'),
        ('Prompt 模板', '8'),
        ('Java 模板文件', '3'),
        ('Agent 模块', '5'),
        ('技术栈模板', '4'),
    ]
    for cat, num in stats:
        row = table.add_row().cells
        row[0].text = cat
        row[1].text = num

    doc.add_page_break()

    # ========== 2. 系统架构与核心流程 ==========
    h = doc.add_heading('', level=1)
    set_heading_style(h.add_run('2. 系统架构与核心流程'), size=16)

    p = doc.add_paragraph()
    t = p.add_run('系统采用 LangGraph 状态机编排 5 个 Agent 的顺序执行，形成完整的代码生成流水线：')
    set_body_style(t)

    flow = doc.add_paragraph()
    flow_text = (
        '\n'
        '[开题报告文本]\n'
        '       ↓\n'
        '┌─────────────────┐\n'
        '│  1. PM Agent    │  解析需求 → 提取项目名、模块列表、技术栈\n'
        '│   (项目经理)     │\n'
        '└─────────────────┘\n'
        '       ↓\n'
        '┌─────────────────┐\n'
        '│ 2. Architect    │  设计数据库 Schema + OpenAPI 契约 + 目录结构\n'
        '│   (架构师)       │\n'
        '└─────────────────┘\n'
        '       ↓\n'
        '┌─────────────────┐\n'
        '│  3. Coder Agent │  串行生成所有模块代码（两阶段+契约注入）\n'
        '│   (代码生成器)   │\n'
        '└─────────────────┘\n'
        '       ↓\n'
        '┌─────────────────┐\n'
        '│ 4. Builder Agent│  编译验证（mvnw clean install）\n'
        '│   (构建验证器)   │\n'
        '└─────────────────┘\n'
        '       ↓ 编译失败？\n'
        '┌─────────────────┐    是 → 最多修复 3 次\n'
        '│  5. Fix Agent   │    否 → 交付\n'
        '│   (修复器)       │\n'
        '└─────────────────┘\n'
    )
    t = flow.add_run(flow_text)
    set_body_style(t)

    p = doc.add_paragraph()
    t = p.add_run('每个 Agent 之间通过 LangGraph 的 AgentState（TypedDict）共享数据。状态字段包括：report_text、tech_stack、modules、db_schema、api_contract、code_files、build_results 等。')
    set_body_style(t)

    doc.add_page_break()

    # ========== 3. 文件清单与作用说明 ==========
    h = doc.add_heading('', level=1)
    set_heading_style(h.add_run('3. 文件清单与作用说明'), size=16)

    # 3.1 根目录
    h2 = doc.add_heading('', level=2)
    set_heading_style(h2.add_run('3.1 根目录文件'), size=14)

    root_files = [
        ('main.py', '系统入口。构建 LangGraph 状态机，定义所有节点函数（parse_report_node、design_architecture_node、code_generation_node、build_verification_node、fix_code_node 等），提供 run_pipeline() 运行完整流程。'),
        ('state.py', '全局状态定义。AgentState TypedDict 声明所有跨 Agent 共享的字段类型，包括 TaskItem、CodeFile、BuildResult 等子类型。'),
        ('config.py', '全局配置中心。定义 LLM 提供商路由（DeepSeek/OpenAI）、各 Agent 默认模型参数、技术栈映射、get_llm_client() 工厂函数。支持 .env 覆盖和运行时手动覆盖。'),
        ('requirements.txt', 'Python 依赖清单。包含 langgraph、langchain-openai、loguru、jinja2、python-dotenv 等核心库。'),
        ('.env', '环境变量配置文件。存储 DEEPSEEK_API_KEY 等敏感信息，不被版本控制。'),
        ('.env.example', '环境变量模板。提供配置示例，新用户复制为 .env 后填写自己的 API Key。'),
        ('run_log.txt', '运行日志文件。记录 main.py 的历史运行输出。'),
    ]
    for fname, desc in root_files:
        add_bold_paragraph(doc, fname, desc)

    # 3.2 agents
    h2 = doc.add_heading('', level=2)
    set_heading_style(h2.add_run('3.2 agents/ — Agent 实现层'), size=14)

    agent_files = [
        ('pm_agent.py', 'PM Agent（项目经理）。解析中文开题报告，调用 LLM 提取结构化需求：project_name、modules、entities、actors、constraints、complexity。输出严格 JSON，带 3 层 fallback 兜底。'),
        ('architect_agent.py', 'Architect Agent（架构师）。基于 PM 输出设计数据库 Schema（SQL）、OpenAPI 契约（YAML）、推荐目录结构。使用原生 OpenAI API 绕过 LangChain Python 3.14 兼容性。新增 schema 为空保护：LLM 不按格式输出时自动生成 fallback schema。'),
        ('coder_agent.py', 'Coder Agent（代码生成器）。核心生成引擎。两阶段生成策略：串行生成各模块，每模块调用 LLM 输出 JSON 数组格式的文件列表。关键改进：契约注入（_extract_contracts）——从已生成模块提取 Repository/Entity API 签名注入后续模块 prompt，降低跨模块不一致。后处理包括：包名统一、去 BOM、Lombok 移除、截断检测。'),
        ('builder_agent.py', 'Builder Agent（构建验证器）。编译验证 Agent。优先使用项目自带的 mvnw（避免系统 Maven 版本问题），超时 600 秒。Windows 中文路径通过 os.chdir 规避。支持 Java（Maven）和 Python（pip + py_compile）两种构建方式。'),
        ('fix_agent.py', 'Fix Agent（编译错误修复器）。基于 SWE-agent 的 ReAct 循环：读取编译日志 → LLM 分析 → 执行修复。支持 4 种修复操作：add/modify/delete/replace_import。只能处理单文件修改，对跨文件依赖错误无效。最多重试 3 次。'),
    ]
    for fname, desc in agent_files:
        add_bold_paragraph(doc, fname, desc)

    # 3.3 prompts
    h2 = doc.add_heading('', level=2)
    set_heading_style(h2.add_run('3.3 prompts/ — Prompt 模板层'), size=14)

    prompt_files = [
        ('prompt_loader.py', 'Prompt 热加载器。基于 Jinja2 的文件系统加载器，支持模板变量渲染（如 {{ module_name }}、{{ db_schema }}）。文件修改后自动失效缓存，无需重启程序。'),
        ('pm_agent.txt', 'PM Agent 的 system prompt。要求 LLM 从开题报告中提取 7 个字段的严格 JSON：project_name、tech_stack_hint、modules、entities、actors、constraints、complexity。'),
        ('architect_agent.txt', 'Architect Agent 的 system prompt。要求 LLM 输出三部分内容：DATABASE_SCHEMA（SQL）、OPENAPI_CONTRACT（YAML）、PROJECT_STRUCTURE（目录树），用 === 分隔。'),
        ('coder_system.txt', 'Coder Agent 的 system prompt（全局）。定义代码规范：禁止 BOM、禁止中文标识符、使用 jakarta 而非 javax、阿里巴巴 Java 开发手册核心规约、公共类强制契约（Result/PageResult/JwtUtil 的精确签名）。要求输出严格 JSON 数组格式。'),
        ('coder_task.txt', 'Coder Agent 的 task prompt（每模块一次）。注入当前模块信息：module_name、db_schema、api_contract、file_list（含契约注入）。定义包名约束、输出格式、依赖说明。'),
        ('builder_agent.txt', 'Fix Agent 的 system prompt。要求 LLM 分析编译错误日志，以 JSON 格式输出修复方案：error_type、root_cause、affected_files、code_changes。'),
    ]
    for fname, desc in prompt_files:
        add_bold_paragraph(doc, fname, desc)

    # 3.4 tools
    h2 = doc.add_heading('', level=2)
    set_heading_style(h2.add_run('3.4 tools/ — 工具层'), size=14)

    tool_files = [
        ('file_writer.py', '安全文件写入器。safe_write_file() 防止 Agent 写出项目目录之外，自动创建父目录，写入前去除 BOM。所有 Agent 的磁盘写操作都通过此模块。'),
        ('retry_wrapper.py', '重试与容错包装器。retry_with_fallback() 装饰器提供指数退避重试（默认 3 次）+ safe fallback。用于包裹不稳定的 LLM 调用，防止网络波动导致 Agent 崩溃。'),
        ('project_init.py', '项目初始化工具。根据技术栈从 templates/ 复制预置骨架到 workspace，用 Jinja2 渲染模板变量（project_name、project_name_lower）。_to_safe_name() 将中文项目名转为安全的英文标识符。'),
        ('lombok_remover.py', 'Lombok 后处理脚本。将 @Data/@Getter/@Setter/@NoArgsConstructor/@AllArgsConstructor 转为显式 getter/setter/构造方法。解决旧版 Maven（3.6.3）与 JDK 21 的 Lombok 注解处理器兼容性 bug。@Builder 直接移除注解（不做转换）。'),
        ('truncation_checker.py', '截断检测器。通过启发式规则（未闭合括号、引号、注解）和 javac 单文件编译检测 LLM 输出是否被截断。在 Coder Agent 后处理阶段运行，发现截断文件时告警。'),
    ]
    for fname, desc in tool_files:
        add_bold_paragraph(doc, fname, desc)

    # 3.5 templates
    h2 = doc.add_heading('', level=2)
    set_heading_style(h2.add_run('3.5 templates/ — 项目模板层'), size=14)

    template_files = [
        ('java-springboot/', 'Java 后端模板。包含 pom.xml（SpringBoot 3.2 + JPA + Security + JJWT 0.11.5 + H2）、Maven Wrapper、mvnw、Application.java、WebConfig.java、application.yml。Coder Agent 在此基础上增量生成业务代码。'),
        ('python-fastapi/', 'Python 后端模板。包含 app/main.py、app/database.py、requirements.txt。'),
        ('vue3-admin/', 'Vue3 管理后台模板。包含 src/api/、src/router/、src/views/、src/stores/、vite.config.js、package.json。'),
        ('wechat-miniapp/', '微信小程序模板。包含 app.js、app.json、pages/、utils/request.js。'),
    ]
    for fname, desc in template_files:
        add_bold_paragraph(doc, fname, desc)

    # 3.6 skills
    h2 = doc.add_heading('', level=2)
    set_heading_style(h2.add_run('3.6 skills/ — 技能规范'), size=14)
    p = doc.add_paragraph()
    t = p.add_run('swe-agent/SKILL.md — SWE-agent 技能规范文档。定义系统必须遵循的 Princeton NLP SWE-agent 原则：ReAct 循环（Reason → Act → Observe）、结构化工具调用、环境反馈驱动修复、细粒度行级编辑而非全文件重写。')
    set_body_style(t)

    # 3.7 test
    h2 = doc.add_heading('', level=2)
    set_heading_style(h2.add_run('3.7 test/ — 测试'), size=14)
    p = doc.add_paragraph()
    t = p.add_run('test/ — 包含 TestLombok.java 等测试文件，用于本地验证 Lombok 移除后处理和编译兼容性。')
    set_body_style(t)

    # 3.8 workspace
    h2 = doc.add_heading('', level=2)
    set_heading_style(h2.add_run('3.8 workspace/ — 输出目录'), size=14)
    p = doc.add_paragraph()
    t = p.add_run('workspace/ — 运行时生成的项目存放目录。每个生成的项目以 project_name 为子目录名（如 campus_secondhand_trade/）。包含完整的后端、前端、小程序代码，以及编译产物 target/。')
    set_body_style(t)

    doc.add_page_break()

    # ========== 4. Agent 协作流程详解 ==========
    h = doc.add_heading('', level=1)
    set_heading_style(h.add_run('4. Agent 协作流程详解'), size=16)

    p = doc.add_paragraph()
    t = p.add_run('4.1 数据流')
    set_heading_style(t, size=12)

    p = doc.add_paragraph()
    t = p.add_run('各 Agent 之间通过 LangGraph 的共享状态 AgentState 传递数据，而非直接函数调用。这种设计解耦了各 Agent，使得单个 Agent 可以独立替换或升级。')
    set_body_style(t)

    table = doc.add_table(rows=1, cols=3)
    table.style = 'Light Grid Accent 1'
    hdr = table.rows[0].cells
    hdr[0].text = 'Agent'
    hdr[1].text = '输入状态字段'
    hdr[2].text = '输出状态字段'

    flow_data = [
        ('PM Agent', 'report_text', 'project_name, tech_stack, modules, requirements_summary'),
        ('Architect Agent', 'project_name, tech_stack, modules, requirements_summary', 'db_schema, api_contract'),
        ('Coder Agent', 'tech_stack, modules, db_schema, api_contract', 'code_files'),
        ('Builder Agent', 'tech_stack, project_name, code_files', 'build_results, project_ready'),
        ('Fix Agent', 'tech_stack, project_name, build_results', '（修改代码文件，无状态输出）'),
    ]
    for agent, inp, out in flow_data:
        row = table.add_row().cells
        row[0].text = agent
        row[1].text = inp
        row[2].text = out

    p = doc.add_paragraph()
    t = p.add_run('4.2 关键改进：契约注入')
    set_heading_style(t, size=12)

    p = doc.add_paragraph()
    t = p.add_run('Coder Agent 的核心挑战是"跨模块代码不一致"——LLM 生成每个模块时看不到其他模块的代码，只能猜测公共类（PageResult/JwtUtil/Repository）的 API 签名。')
    set_body_style(t)

    p = doc.add_paragraph()
    t = p.add_run('解决方案：每生成一个模块后，自动提取该模块的 Repository 接口方法签名和 Entity 字段列表，注入到后续模块的 prompt 中。这样 LLM 看到的是"真实的 API"而非"猜测的 API"。')
    set_body_style(t)

    p = doc.add_paragraph()
    t = p.add_run('为防止 prompt 膨胀，契约摘要设置了总长度预算（2500 字符），按优先级排序：Repository > common > entity > dto > util。预算不足时只保留最关键的 Repository 和 common 类。')
    set_body_style(t)

    p = doc.add_paragraph()
    t = p.add_run('4.3 错误处理与兜底')
    set_heading_style(t, size=12)

    p = doc.add_paragraph()
    t = p.add_run('系统设计了四层容错机制：')
    set_body_style(t)

    items = [
        'LLM 调用层：retry_with_fallback 装饰器提供 3 次指数退避重试 + safe fallback（如 schema 为空时返回默认建表语句）。',
        'Agent 层：每个 Agent 的节点函数都有 try/except，异常导向 error_handler_node 而非崩溃。',
        '状态机层：LangGraph 的 MemorySaver 支持检查点，流程中断后可从断点恢复。',
        'Fix 层：Builder 编译失败后，Fix Agent 最多尝试 3 次自动修复，3 次失败后人工介入。',
    ]
    for item in items:
        p = doc.add_paragraph(item, style='List Bullet')
        for run in p.runs:
            set_body_style(run)

    doc.add_page_break()

    # ========== 5. 关键设计决策 ==========
    h = doc.add_heading('', level=1)
    set_heading_style(h.add_run('5. 关键设计决策'), size=16)

    decisions = [
        ('串行生成而非并行', 'Coder Agent 最初使用 ThreadPoolExecutor(max_workers=3) 并行生成模块，但 DeepSeek API 有并发限制，并行请求会全部挂起。改为串行后稳定性大幅提升。'),
        ('Lombok 后处理而非禁用', '模板 pom.xml 保留 Lombok 依赖，但生成后用 lombok_remover.py 将注解转为显式代码。这样 LLM 生成时可以用简洁的 @Data，同时兼容旧版 Maven。'),
        ('Maven Wrapper 优先', 'Builder Agent 优先使用项目自带的 mvnw，避免系统 Maven 3.6.3 与 JDK 21 的兼容性 bug。'),
        ('Architect 绕过 LangChain', 'Architect Agent 直接使用 openai 库调用 API，绕过 LangChain 在 Python 3.14 下的 Pydantic V1 兼容性警告和潜在阻塞。'),
        ('自动确认节点', 'human_review_req_node 和 human_review_design_node 目前都是自动 approve，用于后台批量测试。生产环境可改为真正的人工确认。'),
        ('H2 内存数据库默认', '模板默认使用 H2 内存库而非 MySQL，降低本地运行门槛。部署生产环境时切换为 MySQL 配置即可。'),
    ]

    for title, desc in decisions:
        p = doc.add_paragraph()
        r = p.add_run(title + '：')
        r.font.bold = True
        set_body_style(r)
        r = p.add_run(desc)
        set_body_style(r)

    # 保存
    output_path = r'C:\Users\20160\auto-graduation\项目文档.docx'
    doc.save(output_path)
    print(f'Word document saved to: {output_path}')


if __name__ == '__main__':
    main()
