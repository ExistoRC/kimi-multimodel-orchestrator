---
description: 联网评估模型库并更新自动分配的公开参考资料，不执行真实模态探测
---

为当前 Kimi Code 模型库更新公开参考资料。这个任务可能消耗主模型 token 和搜索配额，只执行资料研究，不启动工程子代理，不调用媒体生成服务，也不把参考分写成实测能力。

按以下步骤处理：

1. 读取 `$KIMI_CODE_HOME/config.toml`（未设置时为 `~/.kimi-code/config.toml`）中的 `[models]`，整理别名、实际模型 ID 和 `capabilities`。不要输出、复制或记录 providers、api_key、OAuth 信息。
2. 读取已有的 `$KIMI_CODE_HOME/model-insights.json`（如果存在），保留其中由真实探测产生的 verified 信息及 checked_at；不要虚构这些信息。
3. 对每个不同的实际模型 ID，使用 WebSearch 和 FetchURL 查询公开资料。只搜索模型 ID、官方技术文档、模型卡、价格、上下文和公开 benchmark；不得发送用户代码、任务正文、提示词或凭据。
4. 来源优先顺序：供应商官方文档/模型卡 > 可核验的独立评测 > 方法透明的社区测试。普通营销文案只能作为低置信度补充。来源冲突时降低 confidence，并在备注中说明。
5. coding、reasoning、vision、speed、cost_efficiency 使用 0–100 的参考分。只有能说明评分依据或归一化方法时才填数字；无法可靠比较时填 `null`。缺失数据不能当作 0 分或满分。
6. 明确区分：
   - `scores`：公开资料形成的参考分，不是统一 benchmark，也不代表当前项目实测表现。
   - `verified`：只有真正执行过对应工具/模态测试才能填写 true/false；未测试保持缺省。
   - `confidence`：high/medium/low 或 0–1，反映资料质量和一致性，不是模型分数。
7. 按以下结构更新 `$KIMI_CODE_HOME/model-insights.json`。写入前如果文件已存在，先在同一目录创建带时间戳的 `.bak` 备份。使用原子替换，保留所有其他未变更模型条目。

```json
{
  "version": 1,
  "generated_at": "<当前 ISO 时间>",
  "models": {
    "<模型别名>": {
      "model": "<实际模型 ID>",
      "scores": {
        "coding": null,
        "reasoning": null,
        "vision": null,
        "speed": null,
        "cost_efficiency": null
      },
      "verified": {},
      "confidence": "low",
      "evidence": [
        {
          "title": "<资料标题>",
          "url": "<可核验 URL>",
          "checked_at": "<当前 ISO 时间>",
          "claims": ["<该来源实际支持的能力和评分依据>"]
        }
      ],
      "notes": "<冲突、缺失或评分方法说明>"
    }
  }
}
```

完成后，简要报告哪些模型有可靠评分、哪些仍缺资料、使用了哪些主要来源，以及哪些能力尚未实测。提醒用户在悬浮窗设置中选择“自动分配（资料 + 规则）”，本地路由会使用这些参考资料和当前模态约束；资料不足时使用回退而不是虚构评分。

用户补充要求：$ARGUMENTS
