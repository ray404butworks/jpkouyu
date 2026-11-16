# 日语私教 · Japanese Immersion Coach

**把“看选项会做”练成“换个场景也会说”。**

面向中文使用者的 N1 中日双语沉浸式日语私教 Skill。通过情景交流理解词汇与语法，在真实表达中纠错，再按第 1／3／7 天复习。日常陪练保持自然交流，考试模式保留 JLPT 训练。

仓库继续使用 **jpkouyu**，新版技能名为 **japanese-immersion-coach**。这是第一阶段的可迁移文件版：教学指令、Project 指令和本地课程记录工具；语音交互取决于当前客户端。

## 直接开始

安装后，在支持本地 Skill 的环境中发送：

~~~text
使用 $japanese-immersion-coach 开始今天的日语陪练，先试 10 分钟。
~~~

| 你说 | 私教会做什么 |
|---|---|
| 开始今天的日语陪练 | 自然聊天、情景词汇、语法互动、角色扮演、旧知识复现 |
| 我们用日语随便聊聊 | 围绕兴趣交流，自然穿插 N1 表达 |
| 复习我之前做错的题 | 从实际提供的错题讲清含义，再换新情境使用 |
| 切换 N1 考试模式 | 词汇、语法、读解或听力训练，按实际作答批改 |
| 中国語で説明して | 用简短中文说明，再接回日语 |
| 今天先到这里 | 立即收课，整理状态、原句、纠错和待复习项 |

默认一课 35–45 分钟，重点 5–8 个词、2–3 条语法；按理解程度调整。只练 10 分钟时减少内容。教学不会每句机械翻译，也不会把聊天变成选择题连考。

## 两种使用方式

### 本地 Skill

需要支持本地 Skill 的客户端；课程归档工具需要 Python 3.10+，仅使用标准库。

将本仓库完整内容放进你的技能目录，文件夹命名为 japanese-immersion-coach。继续使用客户端已配置的技能目录即可。例如，在已有的 CODEX_HOME/skills 下克隆：

~~~powershell
$jpSkillDir = Join-Path $env:CODEX_HOME 'skills\japanese-immersion-coach'
git clone https://github.com/ray404butworks/jpkouyu.git $jpSkillDir
~~~

仅在 CODEX_HOME 已设置时使用上例；也可以从 GitHub 下载 ZIP 后解压到已配置的技能目录。最终路径应是 japanese-immersion-coach/SKILL.md，避免多嵌套一层。重新打开客户端或新建聊天，确认技能可见。

原来安装为 jpkouyu 的用户应在备份后换成新版文件夹；已有课程数据保留在原处，避免同时启用两个重复教学入口。本次仓库升级不会自动修改你本机已安装的技能。

### ChatGPT Project

复制 [项目指令](docs/PROJECT-INSTRUCTIONS.md) 到项目设置中的指令。将你愿意使用的学习画像、真实错题和最近课程总结添加为项目来源，然后在项目新聊天中说「开始今天的日语陪练」。支持语音的客户端可自行开启语音。

结束后把文字总结保存到项目来源；下次先确认教练读到了上次记录。若未读到，粘贴上次总结继续。粘贴项目指令不等于安装原生 Skill，也不保证语音转录或跨会话记录自动持久化。

## 教学与复习

- 情景输入 → 理解 → 交流 → 主动表达 → 纠错 → 间隔复现 → 考试迁移。
- 六种知识状态：未学习、已接触但不理解、被动理解、提示后使用、独立使用、需要重新巩固。
- 首次接触后第 1／3／7 天换语境复现；遗忘后安排次日再试，错过的复习不一次堆满。
- 选择题答对、跟读和即时模仿不会直接升级为独立使用。没有机会表达时标记未观察。
- 只有听到原始音频才能判断发音。转写内容不能证明音调、长音、促音或真实听辨表现。

见 [教学规则](references/teaching-method.md)、[复习策略](references/review-policy.md)、[模拟课程](examples/immersion-demo.md)。公开版不含个人成绩、错题账本、考试日期或私人学习画像。请在本地填写 [画像模板](references/learner-profile.md)。

## 本地保存与恢复

新版采用独立 JSON 课程文件，不需要数据库、网站或外部 API。明确指定一个私有数据目录，并在所有命令中保持一致：

~~~powershell
$jpData = 'G:\AI\OpenAI\Workspaces\japanese-immersion-coach-data'
python scripts/coach.py archive --data-dir $jpData --input '课程记录.json'
python scripts/coach.py due --data-dir $jpData --on 2026-11-17
~~~

其他系统换成自己的可写绝对路径；--on 使用实际复习日期，省略时取电脑本地日期。输入格式和证据要求见 [课程记录规范](references/session-schema.md)。命令应在技能目录运行，或使用脚本的绝对路径。

同 ID、同内容重复保存不重复记课；同 ID 不同内容拒绝覆盖。due 只读取记录，给出知识点、当前状态、到期日期和复习轮次，不擅自修改成绩。不会推送通知，也不会自动监听语音。

## 旧版兼容

原场景预习卡、复习台、每日小说一句及其脚本完整保留，见 [旧版使用说明](docs/legacy-workbench.md)。旧记录仍用原 workbench.py 和原数据目录读取；新版六级状态与间隔复习使用 coach.py 和独立目录。此次不迁移、不覆盖旧历史。

## 验证边界

本仓库提供可检查的教学规范和可运行的本地记录工具。本地自动检查可验证数据保存、幂等、证据约束和复习日期；不能证明手机语音里的中日切换、原生 Skill 自动调用或 Project 自动找到旧记录。这些仍需在实际客户端体验后验收。

开发检查：python -m unittest discover -s scripts -p "test_*.py"。旧版每日短句检查：node --test scripts/test_daily_quotes.cjs。
