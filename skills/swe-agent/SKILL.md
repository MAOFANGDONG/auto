# SWE-agent 开发原则 Skill

> 来源：Princeton NLP 的 [SWE-agent](https://github.com/princeton-nlp/SWE-agent)
> 核心思想：用 **环境反馈驱动** 的 ReAct 循环替代一次性生成，用 **结构化工具调用** 替代自由文本输出。

---

## 一、核心机制：ReAct 循环

所有 Agent 必须遵循 **Reason → Act → Observe → Repeat** 的循环，禁止一次性生成全部内容后不再修正。

```
Reason: 分析当前状态和目标差距
  → Act: 执行最小可行的原子操作
  → Observe: 读取环境返回的结果
  → (循环)
```

### 应用示例

**Coder Agent（错误做法）**：
```
一次性生成 20 个文件的完整代码 → 写入磁盘 → 结束
问题：包名写错、import 缺失、文件截断 → 无法编译
```

**Coder Agent（正确做法）**：
```
Reason: 用户管理模块需要 User 实体 + Repository + Service + Controller
Act: 生成 User.java 实体类
Observe: 后处理脚本检查发现包名含中文
Reason: 包名不合规，需要修正
Act: 重新生成 User.java，包名改为 com.example.campustrade.entity
Observe: 包名正确，但缺少 @Table 注解
Act: 补充 @Table(name = "users")
...
```

---

## 二、Agent-Computer Interface (ACI) 原则

### 2.1 禁止自由文本输出代码

LLM 不直接输出 `// File: path\ncontent` 这种自由文本。而是输出**结构化的工具调用**，由外部程序解析并执行。

**推荐格式（Function Calling / JSON）**：
```json
{
  "action": "write_file",
  "path": "src/main/java/.../User.java",
  "content": "package ...;\n..."
}
```

**Fallback 格式（如果模型不支持 function calling）**：
```
<action>write_file</action>
<path>src/main/java/.../User.java</path>
<content>
package ...;
...
</content>
```

### 2.2 原子操作工具集

每个 Agent 只能使用预定义的原子操作，不能绕过工具直接输出代码。

| 工具 | 说明 | 适用 Agent |
|------|------|-----------|
| `view` | 查看文件/目录内容 | 所有 |
| `create` | 创建新文件 | Coder |
| `edit` | 替换文件的指定行范围 | Coder / Fix |
| `search` | 在代码库中搜索类/方法/文本 | 所有 |
| `run` | 执行命令（mvn / javac / npm） | Builder |
| `report` | 输出分析结果/决策 | PM / Architect |

---

## 三、环境反馈驱动（Observation）

### 3.1 每个 Act 必须有 Observation

Agent 执行操作后，必须等待环境返回 Observation，再根据 Observation 决定下一步。禁止"盲写"。

**Builder Agent 的 Observation 规范**：
```json
{
  "stage": "java_compile",
  "success": false,
  "errors": [
    {
      "file": "src/.../User.java",
      "line": 15,
      "message": "找不到符号: UserRepository",
      "severity": "ERROR"
    }
  ],
  "stdout": "...",
  "stderr": "..."
}
```

### 3.2 Fix Agent 必须读取 Observation

Fix Agent 的工作流程：
```
1. view(编译日志) → 提取所有 ERROR
2. Reason: 分析每个错误的根因
3. search(相关文件) → 定位需要修改的位置
4. edit(修复代码) → 最小修改
5. run(重新编译) → 获取新 Observation
6. 如果还有错误 → 回到步骤 1
```

---

## 四、细粒度编辑原则

### 4.1 优先 edit 而非重写

修改代码时，**只修改出错的行**，不要重写整个文件。

**错误做法**：
```
发现 User.java 第 15 行 import 错误 → 重新生成整个 User.java
```

**正确做法**：
```
发现 User.java 第 15 行 import 错误 → edit(第15行, "import com.example.campustrade.repository.UserRepository;")
```

### 4.2 修改前必须先 view

Agent 在 edit 之前，必须先 view 目标文件的当前内容，确认修改位置的上下文。

---

## 五、Prompt 设计规范

### 5.1 所有 Agent Prompt 必须包含

1. **ReAct 指令**：明确告诉 LLM "你必须先 Reasoning 再 Action"
2. **可用工具列表**：告诉 LLM 它能调用哪些工具
3. **Observation 格式**：告诉 LLM 它会收到什么样的反馈
4. **禁止项**：明确列出不能做的事（如禁止中文包名、禁止 Lombok 等）

### 5.2 Coder Agent 的 Prompt 必须包含

```
## 工作流（必须遵循）
1. 每次只生成一个文件
2. 生成后等待系统返回校验结果
3. 如果有错误，只修改出错的行，不要重写整个文件
4. 确认当前文件无误后，再生成下一个文件

## 可用工具
- create(path, content): 创建新文件
- edit(path, start_line, end_line, new_content): 修改文件的指定行
- view(path): 查看文件内容

## 输出格式（严格）
你必须以 JSON 格式输出：
{"action": "create/edit", "path": "...", "content": "..."}
```

---

## 六、当前项目应用清单

| 问题 | SWE-agent 原则 | 当前状态 | 待改进 |
|------|---------------|---------|--------|
| 包名乱码 | 结构化输出 + 校验 | 后处理脚本兜底 | Coder Prompt 改为 JSON 输出 |
| Lombok 失效 | 环境隔离/反馈驱动 | 禁止 Lombok | 可用 Docker 恢复 Lombok |
| 文件截断 | 细粒度 edit + view | 无 | 接入流式输出 + 自动补全检测 |
| Fix Agent 无效 | ReAct 循环 | 仅计数 | 读取编译日志 → LLM 分析 → edit |
| 重复生成公共类 | view 已有文件 | 无 | Coder 先 view 已生成文件列表 |
| import 错误 | 环境反馈 → edit | 手动修复 | Fix Agent 自动读取编译错误定位 |

---

## 七、参考资源

- [SWE-agent 论文](https://arxiv.org/abs/2405.15793)
- [SWE-agent GitHub](https://github.com/princeton-nlp/SWE-agent)
- [ReAct 论文](https://arxiv.org/abs/2210.03629)
