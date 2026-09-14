# 反馈系统 v2 · 设计稿

> 目标：把"反馈"从一个表单升级成**可分来源归类、能追踪、能双语回复**的闭环。
>
> **进度（2026-09-14 更新）**：P0 + P1 已实现——服务端 `source`/`locale`/scope/双语列/
> DeepSeek 翻译（`996e508`）；网站的两个来源 tab、双语回复与 AI 翻译按钮、反馈页的
> `littletiles` 模块与惯用语言、LT 页面反馈入口、LT 内容的多语言 AI 补齐；
> 客户端「我的反馈」+ 启动自动查 + 已读 + 译文优先显示。
> 决定已定：接 DeepSeek（key 在服务端配）、来源分两个 tab、网站 LT 页面加反馈入口。

## 1. 你的诉求 → 落点

| 诉求 | 落在哪儿 | 现状 |
|---|---|---|
| 后台按来源分两个 tab：网站反馈 / LittleTiles Reader 反馈 | 服务端加 `source`，页面加一排 scope tab | **已完成**（两个 tab） |
| 网站里 littletiles 模块的反馈也算进 LT | 网站的反馈表单加 `littletiles` 选项，LT 页面进入时默认选中 | **已完成** |
| 与其它业务区分开 | 同上（`account/site/server/web` 归"其它"一栏） | 待做 |
| 后台能下载日志附件 | 已实现：详情弹窗「日志附件」+ 下载按钮，走 `POST /feedback/attachment?bugId=`（需 `bug:manage`） | **已完成** |
| 软件里能查数据码、自动记录、启动自动查状态、已解决弹窗、查看后标已读 | 客户端「我的反馈」+ 启动静默检查 | **已完成** |
| 惯用语言选项 + 回复双语（中文原文 + 用户语言对照） | 服务端 `locale` + 译文字段；后台双栏回复（含 AI 翻译按钮）；客户端译文在前、可展开中文 | **已完成** |
| 其它反馈模块同步这套 | 网站的反馈页与后台回复组件共用同一套字段与渲染 | **已完成**（反馈页 + LT 内容管理） |

已确认的现状（写设计时核对过代码）：

- 服务端 `feedback_bug` 已有：`type / title / description / module / severity / contact /
  page_url / user_agent / data_code / status / opinion / resolution / …`，本轮又加了
  **附件 4 列 + 一次性上传凭证 2 列**（见 `deploy/sql/feedback_attachment.sql`）；
- `POST /feedback/submit` 公开、`POST /feedback/query?dataCode=` 可匿名查进度（脱敏返回）；
- 网站的反馈表单（`BugFeedbackView.vue`）模块选项是 `web/server/account/site/other`，
  **没有 littletiles**；后台（`FeedbackManageView.vue`）目前只有一排**状态** tab；
- 站点的 i18n 已有 7 种语言（zh-cn / zh-tw / en / ja / ko / de / fr），
  应用端也是这 7 种——**两边语言代码对得上**，这是"惯用语言"能落地的前提。

## 2. 数据模型（服务端，`feedback_bug`）

新增 4 列（`deploy/sql/feedback_v2.sql`）：

| 列 | 类型 | 说明 |
|---|---|---|
| `source` | varchar(16) default `'web'` | `web`=网站提交，`app`=桌面客户端提交 |
| `locale` | varchar(16) default `'zh-Hans'` | 提交者惯用语言，取值限定 7 种之一 |
| `opinion_i18n` | varchar(1000) | 处理意见的**用户语言**译文 |
| `resolution_i18n` | varchar(2000) | 处理方案的**用户语言**译文 |

另外：`module` 增加取值 **`littletiles`**（网站的 LT 页面/模块反馈用它）。

> 为什么不新增"LT 反馈表"：反馈的处理流程（状态机、附件、数据码、双语回复）完全一样，
> 分表只会让后台多一套 CRUD。用 `source` + `module` 两个维度就够分类了。

**归类规则（后台 tab 的判定）**：

```
LT 反馈   = source = 'app' OR module = 'littletiles'
网站反馈 = source = 'web' AND module <> 'littletiles'
其它业务 = module IN ('account', 'site', 'server')
```

## 3. 接口变更（都是**追加式**，老前端不受影响）

| 接口 | 变更 |
|---|---|
| `POST /feedback/submit` | 请求加 `source`（默认 web）、`locale`（默认 zh-Hans）；响应不变 |
| `POST /feedback/page` | 请求加 `scope`：`all`(默认) / `lt` / `web` / `other`；`module` 关键字过滤保留 |
| `POST /feedback/detail` · `/query` | 响应加 `source` / `sourceName` / `locale` / `localeName` / `opinionI18n` / `resolutionI18n` |
| `POST /feedback/review` | 请求加 `opinionI18n` / `resolutionI18n`（可空：空 = 只回中文） |

`locale` 的合法性由服务端收敛（不在白名单就按 `zh-Hans`），避免脏数据进库。

## 4. 后台界面（`FeedbackManageView.vue`）

```
BUG 反馈
[全部] [LittleTiles Reader] [网站] [其它业务]      ← 新增：来源 tab（scope）
[待处理] [处理中] [已解决] [已驳回] [全部]         ← 原有：状态 tab（两者叠加筛选）
[类型 ▾] [关键字 ______] [搜索]

表格：编号 | 来源徽标 | 惯用语言 | 类型 | 标题 | 严重 | 提交人 | 状态 | 提交时间 | 操作
              ↑新增     ↑新增
```

- **来源徽标**用颜色区分（LT = 草绿，网站 = 蓝，其它 = 灰），一眼能扫；
- **惯用语言**显示成 `繁體中文 (zh-Hant)` 这样的小字，回复时不用再猜；
- 详情弹窗新增两块：
  - 「日志附件」（已实现）：文件名 + 大小 + SHA-256 + 下载按钮；
  - 「回复（双语）」：左边**中文原文**（你写的），右边**用户语言译文**，
    下面一行提示"用户惯用语言：繁體中文"；译文为空时按钮上给个温和的提醒
    （不强制——有些反馈用中文回就够了）。
- 回复框旁给两个小按钮：**「复制翻译提示词」**（把中文原文 + 目标语言拼成一段提示词，
  方便你丢给 AI 翻译后粘回来）和「从中文原文复制」（手工改写时省事）。

## 5. 客户端（桌面应用）

### 5.1 提交时带上来源与惯用语言

- `source = "app"`（写死在 `app/report.py`）；
- `locale = i18n.current()`（用户在应用里选的语言）→ 后台回复时按它选译文。

### 5.2 「我的反馈」：本地记录 + 状态追踪

`config/reports.json` 每条**扩展**为：

```json
{
  "bugNo": "20260914-003", "dataCode": "WXYZ2345",
  "title": "…", "type": "bug", "severity": "LOW",
  "createdAt": "2026-09-14 20:20:26",
  "logCopy": "logs/reports/2026-09-14_2020_20260914-003.txt",
  "status": "pending", "statusName": "待处理",
  "opinion": null, "resolution": null,
  "opinionI18n": null, "resolutionI18n": null, "locale": "zh-Hant",
  "lastCheckedAt": null, "seenAt": null
}
```

菜单入口：**帮助 → 我的反馈**（列表 + 操作）：

| 列 | 说明 |
|---|---|
| 未读点 | `seenAt` 为空 → 画一个亮点 |
| 时间 / 编号 / 标题 | 提交时记下的 |
| 状态 | 待处理 / 处理中 / 已解决 / 已驳回（**未查过**显示"—"） |

按钮：**查看详情**（主动查询，拿到最新回复）、**复制数据码**、**打开本机日志**、**删除记录**。

### 5.3 启动时的自动查询（状态机）

```
启动 → 取 reports.json 里 seenAt 为空 且 (状态未知 或 未解决) 的条目
     → 静默 POST /feedback/query?dataCode=…（带 3 秒超时，失败不打扰）
     → 若状态变成 resolved/rejected：
            弹一次窗口：「你反馈的 #20260914-003 已解决」
            [查看] → 打开详情弹窗（这时才主动查一次拿全文回复）
                    → 详情关闭后写 seenAt（本机标记已读）
            [以后再说] → 不写 seenAt，下次启动还会提示一次
     → 若仍是 pending/in_progress：只更新状态，不弹窗
```

- **只有 `seenAt` 为空的条目会自动查**；看过之后不再自动查（省请求、也不烦人），
  想再看就点「查看详情」（那永远是真查）；
- 一天最多自动查一次（沿用"检查更新"的 `last_update_check` 思路，新增
  `last_feedback_check`），避免每次开都发请求；
- 断网/服务器 502：静默跳过，不弹错误（和检查更新一致）。

### 5.4 详情弹窗（双语渲染）

```
状态：已解决（2026-09-15 10:00）
—— 处理方案 ——
[用户语言译文]           ← 有译文就显示这段
▸ 查看中文原文（对照）    ← 折叠展开，永远给中文原文，便于核对
—— 处理意见 ——
同上
```

译文缺失时：直接显示中文原文，并标注"（本条回复只有中文）"——**不假装有译文**。

## 6. "其它反馈模块同步" 的具体清单

| 位置 | 改什么 |
|---|---|
| `Sources/web/src/views/public/BugFeedbackView.vue` | 模块选项加 `littletiles`；加**惯用语言**选择（默认站点语言，可改）；从 LT 页面进入时预选 `littletiles` |
| `Sources/web/src/views/private/system/FeedbackManageView.vue` | 来源 tab、来源徽标、惯用语言列、双语回复栏（§4） |
| `Sources/web/src/api/feedback_module/FeedbackAPI.ts` | 类型补 `source/locale/opinionI18n/resolutionI18n/scope`；模块类型加 `littletiles` |
| 站点 i18n 词条（7 语言） | `feedback.moduleLittletiles`、`feedback.locale*`、`feedback.replyI18n*` |
| 应用端 i18n | 「我的反馈」「查看中文原文」「本条回复只有中文」「你反馈的 %s 已解决」等约 20 条 × 7 语言 |
| 站内通知（若将来把"已解决"推给登录用户） | 复用同一套双语字段渲染；本轮不做（应用是匿名提交，没有账号绑定） |

## 7. AI 翻译怎么落地（**需要你选**）

| 方案 | 做法 | 成本 | 备注 |
|---|---|---|---|
| **A 人工粘贴**（建议先做） | 后台给「复制翻译提示词」按钮，你丢给任意 AI 翻译，把结果粘进"译文"框 | 0 | 不引入任何密钥；回复质量你还能顺手把关 |
| B 服务端接 LLM | 后台加「一键翻译」按钮，服务端调 LLM API（需要 key、计费、超时与失败处理） | API 费用 + 一点运维 | 若你希望站长点一下就出译文，这个更省事 |
| C 只在客户端翻 | 客户端拿到中文原文后本地翻译 | 无 | ❌ 不推荐：译文质量不可控，且用户可能看不到你真正想表达的意思 |

## 8. 分期与验收

**P0（半天）**：服务端 `source`/`locale`/`scope` + 后台来源 tab 与徽标；客户端提交带
`source`/`locale`；「我的反馈」列表 + 启动自动查 + 已解决弹窗 + 查看后标已读。

**P1（半天）**：双语回复（服务端 2 列 + 后台双栏 + 客户端折叠中文原文）；
网站反馈页加 `littletiles` 模块与惯用语言选择。

**P2（视决策）**：AI 一键翻译（方案 B）。

验收要点：

1. 应用里提一条 LT 反馈（语言选繁體中文）→ 后台「LittleTiles Reader」tab 里能看到，
   带 `繁體中文` 徽标；网站提一条（模块选 littletiles）→ 也在同一个 tab；
2. 后台回一条带译文的回复 → 应用「我的反馈 → 查看详情」能看到译文，
   并能展开中文原文对照；把译文留空时，显示中文原文并注明；
3. 应用重启 → 自动查到"已解决"→ 弹一次提示；点「查看」后**再重启不再提示**
   （`seenAt` 已写），但手动「查看详情」仍能拿到最新回复；
4. 断网启动不弹任何错误。

## 9. 待你拍板

1. **AI 翻译**：先做方案 A（人工粘贴 + 提示词按钮），还是要我按 B 接 LLM API
   （需要你给 key 与月度预算上限）？
2. **tab 命名与分栏**：`LittleTiles Reader / 网站 / 其它业务` 三栏够吗？
   还是只要两栏（LT / 其它），把网站反馈并进"其它"？
3. **网站的 LT 反馈入口**：要我在 LT 页面加一个"反馈这个问题"的入口（自动带上
   `module=littletiles` + 当前页面 URL），还是只把模块选项加进现有反馈页？

## 10. 已知约束（写在这里免得以后忘）

- 应用是**匿名**提交（没有账号体系），所以"已读/未读"只能存在**本机** `reports.json`，
  换机器或清空数据就丢——这是当前的取舍，不是缺陷；
- `dataCode` 是**唯一**的追踪凭证，本地删掉就找不回进度（设计上不做服务端找回）；
- 双语回复需要"两份文本"，本身不增加泄露面；`locale` 只是语言偏好，不含身份信息。
