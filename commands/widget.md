---
description: 显示、隐藏或打开多模型工程状态悬浮窗设置
---

根据参数执行本地悬浮窗操作：空参数或 `show` 为显示，`hide` 为隐藏，`settings` 为打开设置页。不要调用模型子代理处理这个本地 UI 请求。

在 Bash 中运行下面的命令，并把最后的 `--show` 替换为对应操作：

```bash
node "${KIMI_CODE_HOME:-$HOME/.kimi-code}/plugins/managed/kimi-multimodel-orchestrator/hooks/widget-lifecycle.mjs" --show
```

如果提示悬浮窗运行环境未安装，运行以下安装器后再唤醒：

```bash
node "${KIMI_CODE_HOME:-$HOME/.kimi-code}/plugins/managed/kimi-multimodel-orchestrator/scripts/install-widget.mjs"
```

用户参数：$ARGUMENTS
