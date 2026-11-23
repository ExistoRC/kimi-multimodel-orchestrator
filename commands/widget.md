---
description: 显示、隐藏或打开多模型工程状态悬浮窗设置，确认后可初始化桌面环境
---

根据参数执行本地悬浮窗操作：空参数或 `show` 为显示，`hide` 为隐藏，`settings` 为打开设置页。不要调用模型子代理处理这个本地 UI 请求。

`hide` 直接执行下面的生命周期命令并将参数改为 `--hide`，无需环境检测或安装。

对于显示或设置请求，先运行只读状态检查：

```bash
node "${KIMI_CODE_HOME:-$HOME/.kimi-code}/plugins/managed/kimi-multimodel-orchestrator/hooks/widget-lifecycle.mjs" --status
```

该检查只读取本地状态并测试 PySide6 是否可导入，不启动下载、不修改配置。读取 JSON 中的 `ready`、`installRequired`、`source`、`platform` 和 `platformVerified`：

- 如果 `ready=true`，执行同一生命周期脚本，将参数改为 `--show` 或 `--settings` 以对应用户请求。
- 如果 `installRequired=true`，明确告诉用户：悬浮窗缺少独立的 PySide6 运行环境；初始化需要联网安装固定版本的桌面依赖，核心路由不依赖该环境。不要只把长命令交给用户自行执行。
- 如果 `platform` 不是 `win32`（或 `platformVerified=false`），同时明确说明 Linux/macOS 尚未完成兼容性验证。
- 在执行安装前，必须征得用户对本次联网初始化的明确确认并等待答复。用户主动执行 `:widget` 本身不等于同意安装依赖。
- 用户确认后，由主代理直接执行以下受管安装器，而不是仅提供命令：

```bash
node "${KIMI_CODE_HOME:-$HOME/.kimi-code}/plugins/managed/kimi-multimodel-orchestrator/scripts/install-widget.mjs"
```

安装成功后，再执行 `--show` 或 `--settings` 唤醒对应界面。安装失败时如实报告错误，不进行无上限重试、不全局安装 PySide6、不修改模型配置。

不得修改 `SessionStart` 行为。后台 `--ensure` 不得调用安装器、联网下载或阻塞新会话；即使用户使用纯 CLI，也保持安静。只有用户显式请求显示/设置并在环境缺失后再次确认，才允许初始化。

用户参数：$ARGUMENTS
