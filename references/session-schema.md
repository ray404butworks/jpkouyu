# 新版课程记录 v1

脚本为本地文件工具，仅使用 Python 标准库。与旧复习台四级状态的数据格式不同，不要把新记录交给 workbench.py。请在所有调用中传同一个私有绝对目录。

以下为**模拟格式示例**，不代表实际学员表现，也不要导入私人历史：

```json
{
  "version": 1,
  "id": "lesson-20261117-001",
  "created_at": "2026-11-17T20:00:00+08:00",
  "language": "ja",
  "mode": "daily",
  "summary": "模拟：讨论活动安排，用新场景区分担忧与证据。",
  "audio_observed": false,
  "pronunciation_notes": [],
  "items": [
    {
      "key": "vocab-kenen-wo-shimesu",
      "kind": "vocabulary",
      "expression": "懸念を示す",
      "observed": true,
      "state": "prompted",
      "evidence": "模拟：学员在完整示范后复述 会場の広さについて、少し懸念があります。",
      "support": "model",
      "is_review": false,
      "independent_correct": false,
      "transfer": false
    }
  ],
  "focus_next": ["换成产品发布场景表达担忧"]
}
```

- id 是唯一课程标识，只能用英文字母、数字、短横线和下划线；同 ID 不同内容拒绝覆盖。
- created_at 是真实课程本地时间，必须带时区；复习日期按其中的当地日期计算。跨时区学习时由教师明确统一记录时区。
- mode：daily／free／mistakes／exam。考试分数可在额外 scores 字段中按题型记录真实正确数和总数；它不驱动口语掌握状态。
- key 是稳定知识标识，后续同一知识点沿用。kind 是 vocabulary 或 grammar。
- observed=false 表示没有公平练习机会，此时只写 key、kind、expression、observed，不写 state 或任何表现断言；已有状态和复习日期不会改变。
- observed=true 时必须有本课真实证据；可以追加 learner_quote、natural、reason_zh 和 reading 等字段。不要从旧范句编造证据。
- support：none／intent_hint／keyword_hint／model。选择题判断与照读不能记录为独立成功。
- independent_correct=true 仅用于无提示、正确的新语境表达，同时要求 state=independent、support=none、transfer=true。
- is_review=true 只用于正式复测。独立成功且已经到期才能推进复习轮次；讲解后的即时复述不算。
- audio_observed=false 时 pronunciation_notes 必须为空。未获得音频不留“发音很好”等判断。
- focus_next 最多三项；未练到的知识点不加入失败记录。

归档：python <技能目录>/scripts/coach.py archive --data-dir <私有绝对目录> --input <课程JSON绝对路径>。

读取：python <技能目录>/scripts/coach.py due --data-dir <同一目录> --on YYYY-MM-DD。

保存后验证文件位于 <数据目录>/coach-sessions/<id>.json，再报告保存成功。读取旧课程从此目录取原始 JSON；due 只输出到期项，不是完整历史。没有到期项不等于没有学习记录。

脚本不后台运行，不自动收集语音、不推送提醒。无脚本环境需手动保存同等字段和第 1／3／7 天日期，并在下一会话实际提供记录。不得把同一目录交给多个未协调的编辑器修改历史。
