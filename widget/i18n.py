from __future__ import annotations

LANGUAGES = {"zh-CN", "en"}

TRANSLATIONS = {
    "当前工程": "Current project",
    "当前项目": "Current project",
    "未知项目": "Unknown project",
    "尚未连接会话": "No session connected",
    "空闲": "Idle",
    "等待新的工程任务": "Waiting for a new engineering task",
    "会话已就绪": "Session ready",
    "会话已关闭": "Session closed",
    "主代理正在理解目标并规划": "The main agent is understanding the goal and planning",
    "主代理正在处理任务结果": "The main agent is processing task results",
    "主代理规划中": "Main agent planning",
    "正在理解目标与拆分任务": "Understanding the goal and splitting tasks",
    "工程进行中": "Engineering in progress",
    "子代理正在执行分配的工作": "Subagents are executing assigned work",
    "仍有子代理工作": "Subagents are still working",
    "子代理已交付，等待主代理验收": "Subagents delivered; waiting for main-agent review",
    "等待授权": "Waiting for authorization",
    "需要处理权限请求后继续": "Handle the permission request to continue",
    "授权已处理，继续执行": "Authorization handled; resuming",
    "待主代理验收": "Pending main-agent review",
    "子代理交付不等于验收通过": "Subagent delivery does not imply acceptance",
    "交付内容仍需主代理验收": "Delivered work still needs main-agent review",
    "本轮结束": "Turn closed",
    "主代理已结束本轮响应": "The main agent has ended this turn",
    "本轮已结束；最终验收以主代理答复为准": "Turn closed; the main agent's final response remains the acceptance record",
    "执行出错": "Execution error",
    "请返回 Kimi Code 查看详情": "Return to Kimi Code for details",
    "已中断": "Interrupted",
    "本轮由用户中断": "The user interrupted this turn",
    "用户中断了当前轮次": "The user interrupted this turn",
    "后台任务状态已更新": "Background task status updated",
    "工作中": "Working",
    "待验收": "Pending review",
    "出错": "Error",
    "已停止": "Stopped",
    " · 关联不确定": " · uncertain association",
    "返回": "Back",
    "子代理与悬浮窗设置": "Subagent and widget settings",
    "保存设置": "Save settings",
    "路由变更从下一次子代理分派生效": "Routing changes apply to the next subagent dispatch",
    "CURRENT / 当前运行配置": "CURRENT / Runtime configuration",
    "ROUTING / 等级与模态模型": "ROUTING / Tier and modality models",
    "编排模式": "Orchestration mode",
    "两级：简单 / 复杂": "Two tiers: simple / complex",
    "单级：统一执行": "Single tier: unified execution",
    "仅按模态": "Modality only",
    "自动分配（资料 + 规则）": "Auto routing (evidence + rules)",
    "自动分配按任务与模型资料选模型；以下仅作为缺少资料时的回退。可用 /kimi-multimodel-orchestrator:evaluate-models 更新公开参考分。": "Auto routing uses task needs and model evidence; these routes are fallbacks when evidence is missing. Use /kimi-multimodel-orchestrator:evaluate-models to update public reference scores.",
    "同一模型可以复用于多个等级或模态，不要求每个选项不同。": "One model may serve multiple tiers or modalities; each selection does not need to differ.",
    "任务": "Task",
    "模型别名": "Model alias",
    "任意等级 · text": "Any tier · text",
    "任意等级 · image": "Any tier · image",
    "任意等级 · video": "Any tier · video",
    "PROFILES / 固定权限档": "PROFILES / Fixed permission profiles",
    "权限档由 Agent 文件中的工具白名单强制执行；此页面不会动态放开工具。": "Agent-file tool allowlists enforce permission profiles; this page cannot dynamically expand tools.",
    "WIDGET / 悬浮窗": "WIDGET / Desktop widget",
    "界面语言": "Interface language",
    "中文": "Chinese",
    "新会话自动启动悬浮窗": "Start the widget automatically for new sessions",
    "窗口始终置顶": "Keep the window always on top",
    "不透明度": "Opacity",
    "正在校验并保存…": "Validating and saving…",
    "正在验证模型能力并将新选择加入子代理池": "Validating model capabilities and adding selected aliases to the subagent pool",
    "隐藏": "Hide",
    "隐藏到系统托盘；可从托盘 M 图标重新唤醒": "Hide to the system tray; click the tray M icon to reopen",
    "设置": "Settings",
    "等待 Kimi Code 工程事件": "Waiting for Kimi Code engineering events",
    "活跃子代理": "Active subagents",
    "本轮耗时": "Turn elapsed",
    "SUBAGENTS / 实时任务": "SUBAGENTS / Live tasks",
    "LOCAL ONLY  ·  数据来自 Kimi Hooks\n完成状态以主代理实际验收为准": "LOCAL ONLY  ·  Data from Kimi hooks\nAcceptance remains with the main agent",
    "暂无活跃子代理任务": "No active subagent tasks",
    "当前无活跃子代理": "No active subagents",
    "返回状态": "Back to status",
    "Kimi 多模型工程状态": "Kimi Multimodel Engineering Status",
    "Kimi 多模型工程状态 · 单击显示/隐藏": "Kimi Multimodel Engineering Status · Click to show/hide",
    "显示 / 隐藏悬浮窗": "Show / hide widget",
    "打开子代理设置": "Open subagent settings",
    "退出悬浮窗": "Quit widget",
}
REVERSE_TRANSLATIONS = {english: chinese for chinese, english in TRANSLATIONS.items()}


def translate(text: str, language: str) -> str:
    if language == "en":
        if text in TRANSLATIONS:
            return TRANSLATIONS[text]
        if text.endswith(" 正在执行子任务"):
            return f"{text.removesuffix(' 正在执行子任务')} is running a subtask"
        if text.startswith("等待授权："):
            return f"Waiting for authorization: {text.removeprefix('等待授权：')}"
        return text
    if text in REVERSE_TRANSLATIONS:
        return REVERSE_TRANSLATIONS[text]
    if text.endswith(" is running a subtask"):
        return f"{text.removesuffix(' is running a subtask')} 正在执行子任务"
    if text.startswith("Waiting for authorization: "):
        return f"等待授权：{text.removeprefix('Waiting for authorization: ')}"
    return text
