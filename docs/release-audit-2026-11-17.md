# 日语私教发布前审计 · 2026-11-17

## 当前结论

已完成代码清理、函数中文注释、运行时组件／字体盘点、Python 安全扫描和本机接口回归。19 项 Python 测试通过；JavaScript 检查通过，覆盖 7 个时区、跨日与夏令时、页面恢复、HTML 转义和特殊场景 ID。1440px 桌面与 390px 手机宽度在真实 Edge 浏览器中可加载课程状态，页面截图经 AI 查看。

**尚未完成人工签收，不能视为最终上线验收通过。** 维护者明确选择保留 14 条文学书摘，目标地区与商业使用授权继续列为人工必查项。本次只准备可供审查的代码与记录，不把 AI 自查称为人工审计。

## 范围与结果

| 检查 | 结果及证据 |
|---|---|
| 无效前端代码 | 删除 4 个未引用的间距变量、未定义的 paper-card 类名及旧命名字体列表；用原生 progress 替代内联样式，兼容严格 CSP；更新失效的旧技能调用名 |
| 字体 | 字体文件数 0、字体资源 0 字节、远程字体请求 0；现用系统通用字体；不声称删除了原本不存在的字体包 |
| 后端废弃接口 | 删除无前端调用的 /api/preferences 写接口和 /api/health 检查接口；仅保留 GET/HEAD 课程读取与固定资源 |
| 中文注释 | 57 个 Python 函数、5 个匿名回调和 46 个 JavaScript 函数／回调均有中文说明，含测试与审计脚本；脚本逐项检查没有遗漏 |
| 依赖与 license | 无第三方运行时 Python 包、npm 组件、CDN 脚本或捆绑字体；详见 [第三方说明](../THIRD_PARTY_NOTICES.md)；文学摘录和素材权利不因依赖数为 0 自动通过 |
| 漏洞扫描 | Bandit 1.9.4 扫描运行脚本和自有 Python 审计脚本；未报告问题；pip-audit 2.10.1 检查空的运行依赖清单，结果 dependencies=[]，这不表示解释器或整机无漏洞 |
| JavaScript 安全检查 | Acorn 8.19.0 解析函数和危险渲染点；生产代码保留一处集中 innerHTML 模板，已逐字段追踪转义并补恶意文本回归；仍列入人工数据流复核 |
| 实际交互 | 真实本机 HTTP 请求验证只读接口、安全响应头、固定资源与拒绝路径；页面已用无私人课程的隔离目录检查，没有访问或修改真实学习历史 |

原 CSS 10,858 字节，清理后 10,798 字节；新增中文注释会增加源码字节，不能把这轮维护宣传为总包体积下降。

## 发现与修复

### SEC-01 · 中 · 闲置写接口与请求来源边界

原 make_handler 存在 do_PUT /api/preferences，前端没有调用，且未校验 Host、Origin。原 serve 允许自定义非回环绑定。对外暴露或被绕过浏览器来源限制时，存在非预期读取／修改记录的风险；并非声称任意网站无需条件就能跨源 PUT。

修复位于 scripts/workbench.py:246 的 make_handler：删除闲置接口，写方法统一 405；trusted_request 校验回环 Host、Origin 与 Sec-Fetch-Site。serve 在写盘前拒绝非回环地址。测试覆盖伪造 Host、跨站 Origin、cross-site 上下文、6 种写方法，以及写请求后原始数据保持不变。

### SEC-02 · 低 · 静态文件暴露面与错误详情

旧 SimpleHTTPRequestHandler 可以提供静态目录中新增的任意文件，也可能跟随符号链接；这不是已经证明可任意读取整个磁盘。旧接口还会把原始异常文字返回浏览器。

现为固定资源白名单，拒绝非白名单路径与符号链接，错误只返回通用说明，页面带 CSP、nosniff 和禁止缓存头。GET 不再在记录缺失时建档。回归覆盖私有哨兵文件、编码越界路径、目录路径、HEAD 和损坏存档的通用错误。

### SEC-03 · 中 · 特殊场景键导致前端异常

原 renderReview 使用普通对象按 topic.id 分组，__proto__ 等名称会命中对象原型并导致页面异常。已改为 Object.create(null)。新增测试同时确认恶意标签只呈现为已转义文本，不生成脚本元素。

### SEC-04 · 低 · Windows 特殊文件名

两套归档输入原先没有显式拒绝 CON、NUL、COM1 等 Windows 设备名；旧版还接受以点开头的 ID。现统一增加设备名检查，旧版 ID 限制为以字母或数字开头且最多 80 字符，并有回归验证。

## 可重复检查

```text
python -X utf8 scripts/release_audit.py
python -m unittest discover -s scripts -p "test_*.py"
node --test scripts/test_daily_quotes.cjs
node scripts/audit_frontend.cjs <独立审计环境的Acorn绝对目录>
python -X utf8 -m bandit scripts/coach.py scripts/workbench.py scripts/release_audit.py -f json
python -X utf8 -m pip_audit -r requirements.txt --no-deps --disable-pip --format json
```

扫描器和 Acorn 只装在独立开发目录，不需要给使用者安装。JSON 证据保留在 [本次审计目录](audits/2026-11-17/)。这些检查不是完整渗透测试，不涵盖操作系统、浏览器、解释器、手机语音客户端或第三方托管环境。

Python 官方明确说明 [http.server 不适合生产公网服务](https://docs.python.org/3/library/http.server.html)。本项目因此限定为本机只读复习工具；此次没有把它改成公网后端，也没有部署公网服务。

## 待真实人工复核

- [ ] 核对代码变更、接口删减与中文注释是否准确，尤其是集中 HTML 模板的数据流。
- [ ] 实际点验课程显示、刷新、复制指令、收课保存与下一次续接；AI 截图查看不能代替使用者体验。
- [ ] 确认 14 条书摘在目标地区、商业用途下的权利及署名义务；此次按维护者选择保留，不标记授权通过。
- [ ] 确认截图与自有图形的权利来源；是否为项目整体选择开源许可证由作者另行决定。
- [ ] 由 Ray 或指定复核人员记录复核日期与结论，再决定合并／上线。
