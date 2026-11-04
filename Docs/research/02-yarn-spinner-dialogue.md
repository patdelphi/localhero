# Yarn Spinner 源码研究：对话虚拟机与宿主状态边界

## 1. 对象与证据

- 仓库：https://github.com/YarnSpinnerTool/YarnSpinner
- 固定 commit：`c5215f86dd5a6761aecbdc9f60f6a6108f91f919`
- 固定版本性质：master 快照，本研究未将其认定为稳定发布版
- 提交时间：2026-10-14T11:31:38+11:00
- 许可证：MIT，见本地 `LICENSE.md`
- 检索日期：2026-11-04
- 本地快照：`research/upstream/yarn-spinner/`
- 证据范围：C# 核心的 `Dialogue`、`VirtualMachine`、变量访问接口与内存变量库。

## 2. 核心问题

1. Dialogue 与 VirtualMachine 如何交付台词、命令和选项。
2. VM 在等待宿主响应时如何暂停和继续。
3. 变量由对话运行时还是宿主持有。
4. 核心运行时是否提供满足本项目需求的完整对话存档和分支机制。

## 3. 核心流程

### 3.1 节点启动与继续

```text
Dialogue.SetNode(nodeName)
    → 加载编译节点并初始化 VM 执行状态
    → VM 执行指令
        → Line：交付宿主显示
        → Command：交付宿主处理
        → Options：收集并交付宿主选择
    → 等待宿主 Continue / 选择结果
    → 恢复指令执行
```

关键索引：

- [`Dialogue.SetNode()`／`Continue()`](https://github.com/YarnSpinnerTool/YarnSpinner/blob/c5215f86dd5a6761aecbdc9f60f6a6108f91f919/YarnSpinner/Dialogue.cs#L810-L921)
- [`VirtualMachine` 加载节点与初始化执行状态](https://github.com/YarnSpinnerTool/YarnSpinner/blob/c5215f86dd5a6761aecbdc9f60f6a6108f91f919/YarnSpinner/VirtualMachine.cs#L339-L380)
- [`VirtualMachine` 主循环](https://github.com/YarnSpinnerTool/YarnSpinner/blob/c5215f86dd5a6761aecbdc9f60f6a6108f91f919/YarnSpinner/VirtualMachine.cs#L442-L494)

### 3.2 Line、Command 与 Options 的宿主交付

- [`Dialogue` 的 Line／Options／Command 宿主处理器](https://github.com/YarnSpinnerTool/YarnSpinner/blob/c5215f86dd5a6761aecbdc9f60f6a6108f91f919/YarnSpinner/Dialogue.cs#L603-L636)
- [`VirtualMachine.RunLine`、`RunCommand`、`AddOption`、`ShowOptions`](https://github.com/YarnSpinnerTool/YarnSpinner/blob/c5215f86dd5a6761aecbdc9f60f6a6108f91f919/YarnSpinner/VirtualMachine.cs#L552-L727)
- [`VirtualMachine` 节点跳转、detour 与调用栈返回](https://github.com/YarnSpinnerTool/YarnSpinner/blob/c5215f86dd5a6761aecbdc9f60f6a6108f91f919/YarnSpinner/VirtualMachine.cs#L859-L889)

**源码事实：** VM 生成结构化的台词、命令或选项，并进入等待宿主推进的状态；宿主不是被动接收最终整段剧情，而是对话执行协议的一部分。

**项目判断：** 这适合映射为“模型／内容运行时提出结构化回应，程序协调器决定是否展示、执行或等待玩家”，但宿主处理器本身并不自动提供事务与审核。

### 3.3 变量存储所有权

`Dialogue` 定义变量访问与存储接口，`MemoryVariableStore` 是一个可选的内存实现；变量不存在时还可从 `Program.InitialValues` 回退取得初始值。

关键索引：

- [`IVariableAccess` 与 `IVariableStorage`](https://github.com/YarnSpinnerTool/YarnSpinner/blob/c5215f86dd5a6761aecbdc9f60f6a6108f91f919/YarnSpinner/Dialogue.cs#L255-L325)
- [`MemoryVariableStore`](https://github.com/YarnSpinnerTool/YarnSpinner/blob/c5215f86dd5a6761aecbdc9f60f6a6108f91f919/YarnSpinner/Dialogue.cs#L331-L438)
- [`VirtualMachine` 变量读写](https://github.com/YarnSpinnerTool/YarnSpinner/blob/c5215f86dd5a6761aecbdc9f60f6a6108f91f919/YarnSpinner/VirtualMachine.cs#L752-L840)

**源码事实：** 变量通过接口读写；内存变量库并不等同于项目级持久化世界数据库。

**研究判断：** 这一所有权边界比“对话脚本私有变量直接代表世界真相”更适合本项目。未来可让对话运行时只访问经权限过滤的知识视图，所有事实写入另走审核与事务管线。

### 3.4 保存与恢复边界

在本批检查的 `Dialogue`、`VirtualMachine` 和变量存储核心路径中，未看到与 Ink `StoryState` 类似的完整对话状态 JSON 保存／恢复协议。变量持久化、游戏状态保存与继续运行所需的外围状态主要由宿主负责。

**证据措辞限制：** 此处结论是“所查核心路径未见”，不是“Yarn Spinner 整个生态绝对不存在任何保存方案”。

## 4. 可借鉴清单

1. **对话 VM 与宿主世界分离。** 对话运行只提出 Line、Command、Options，不天然拥有世界事实。
2. **结构化交付而非纯文本解析。** 项目开放人物对话也应保留说话者、意图、可见信息、候选行动等结构。
3. **变量访问接口。** 可用只读知识视图替代让 NPC 或模型直接读取完整世界数据库。
4. **显式等待状态。** 选项等待、命令等待与玩家自由输入等待应由程序状态机明确表达。
5. **宿主决定继续。** 模型生成结束不等于行动已提交，也不等于场景自动推进。

## 5. 不采用或不能直接等同的机制

1. 不把 `MemoryVariableStore` 作为本项目权威存储。
2. 不允许 Yarn Command 未经程序校验直接提交案件事实或全球正典。
3. 不把对话节点的局部条件变量自动提升为人物认知、传闻或事实；这些信息类型仍需显式建模。
4. 不假定核心 VM 已提供多分支存档、事件回放或内容版本迁移。
5. 当前不引入 Yarn Spinner 依赖；先借鉴其宿主协议边界。

## 6. 对架构 2.0 的候选启示

- 将 NPC 对话返回协议拆为：可见台词、情绪／表达元数据、候选意图、事实提案和宿主命令；只有台词可直接展示，其余分别校验。
- 为对话运行时定义窄接口：读取当前人物知识视图，不读取主持人秘密；写入只产生提案，不直接修改权威事实。
- 存档若未来嵌入对话 VM，需单独保存节点、指令位置、待处理选项／命令等执行状态，并与世界事件日志关联。

## 7. 证据限制

- 固定的是 master 快照，不是经过本研究验证的稳定发行版本。
- 未逐行研究编译器、所有语言绑定、Unity 集成或全部扩展包。
- 未实测各宿主实现的存档能力，因此不能将核心运行时结论外推到所有生态组件。
- 本批只证明核心边界与调用链，不评价其完整内容生产能力。
