# 检查更新与反馈上报（结合 inception-work 服务器现状的评估）

服务器仓库：`inception-work`（Spring Boot 4 + MySQL，接口前缀 `/api`，
统一响应 `{success, payload, error_type, error_code, error_message}`）。

下面先列**服务器现在已有什么**，再逐个需求说清"现在能做到哪一步、还缺什么"。

## 1. 服务器现状（已实测代码，不是猜的）

| 能力 | 接口 | 公开 | 关键约束 |
|---|---|---|---|
| 提交反馈 | `POST /api/feedback/submit` | ✅ 免登录（匿名可提） | `title` ≤128、`description` ≤2000，超出直接报错；`type` ∈ bug/suggestion；`module` ∈ **web/server/account/site/other**（不认别的值）；`severity` ∈ LOW/MEDIUM/HIGH/CRITICAL；返回 `{bugId, bugNo, dataCode}` |
| 查反馈进度 | `POST /api/feedback/query?dataCode=XXXX` | ✅ | 凭 8 位数据码，返回脱敏内容（不含提交人/联系方式） |
| 后台处理 | `/api/feedback/page|detail|review` | ❌ | 需要 `bug:manage` |
| 客户端下载项 | `GET /api/public/lt-read/downloads` | ✅ | **只有两个平台**：`windows`、`macos-arm`；字段 `version / downloadUrl / note / ready` |
| 静态文件 | `GET /uploads/**` | ✅ 只读 | 映射到 `app.upload-dir`，**没有公开上传接口**（写入口都需要登录后台） |

编号规则 `YYYYMMDD-NNN`；数据码是 8 位大写字母数字（去掉了 0/O/1/I）。

## 2. 需求评估

### 2.1 检查更新 —— 现在就能做，但信息量有限

**能用**：`/public/lt-read/downloads` 已经给出每个平台当前发布的版本号与下载地址，
客户端拿自己的版本一比就能得出"有没有新版 + 去哪儿下"。

**缺**：

| 想显示的 | 服务器现在有没有 | 建议 |
|---|---|---|
| 最新版本号 | ✅ `version`（形如 `v1.0.0`，可能为空） | 客户端做版本号归一化（去掉 `v` 前缀、支持 `1.2.3-beta`） |
| 下载地址 | ✅ `downloadUrl`（`ready=false` 表示还没配好） | — |
| 备注（大小/说明） | ✅ `note` | — |
| **更新日志 / 发布日期** | ❌ | `lt_read_download` 加 `notes`（TEXT）、`published_at` |
| **最低支持版本 / 强制更新** | ❌ | 加 `min_version`，或新增 `/public/app/version` 统一返回 |
| 渠道（stable/beta） | ❌ | 需要再加字段；暂不做 |

结论：**先用现有接口做"有新版 → 提示 + 打开下载页"**，把上面三列当作后续服务端小改动。
客户端不缓存下载包（`UploadPackage` 那一套是给你自己打包用的，应用只跳转）。

### 2.2 BUG 反馈 + 自动提交日志 —— 反馈能提，日志要绕一下

**日志附件：服务端已实现**，走两段式，附件**不进** `description`：

```
1) POST /feedback/submit  { …, "wantAttachment": true }
   → { bugId, bugNo, dataCode, uploadToken }        // 凭证 30 分钟、用一次即失效
2) POST /feedback/attach  multipart: uploadToken + file
   → { name, size, sha256 }                          // 后端重算 sha256，对得上才算收全
3) 后台 POST /feedback/attachment?bugId=  下载（需 bug:manage，流式返回）
```

落盘规则（见服务器仓库 `deploy/sql/feedback_attachment.sql` 与
`FeedbackServiceImpl`）：

- 目录：`app.feedback.attach-dir`（默认 `~/inception-work/feedback-attachments`）——
  **故意不放** `app.upload-dir`，因为那个目录挂在 `/uploads/**` 上是公开可读的，
  而日志里带路径，不该让人猜到 URL 就能下；
- 大小/类型：默认 ≤ **8 MB**（`app.feedback.attach-max-bytes`），只收
  `tar.gz / tgz / zip / log / txt`；
- 详情接口只回 `hasAttachment / attachmentName / attachmentSize / attachmentSha256`，
  不暴露落盘路径；后台页面在多了一条「日志附件」区块 + 「下载日志附件」按钮。

客户端（`app/report.py`）对应做四件事：

1. 取**最近 24 小时**动过的日志（按 mtime，不按文件名——凌晨启动、现在还在写的那份也要算）；
2. **先脱敏再进包**（家目录 → `~`、绝对路径只留末两级），包内附一份 `README.txt`
   （版本、系统、时间窗、清单），管理员不查库也能看懂；
3. 上限按**成品包**算（默认 8 MB）：超了先丢最旧的，连一份都放不下时只留尾部并在
   文件名与 README 上标明；上次打的包不会被再包一遍（排除 `*.tar.gz/zip`）；
4. 附件上传失败**不影响"反馈已提交"**——编号与数据码照给，并提示本机那份包的路径。

来源与语言（已实现）：客户端提交时带 `source=app` 与 `locale=当前界面语言`，
后台按来源分两个 tab（LittleTiles Reader / 网站），回复可以"中文原文 + 用户语言译文"
成对保存。AI 翻译用的是 DeepSeek，**key 在后台「系统管理 → AI 翻译设置」页面里配**
（存 `sys_config` 表，改完立即生效、不必重启；环境变量 `APP_AI_APIKEY` 只是兜底）。

## 3. 客户端怎么做（已实现）

| 模块 | 职责 |
|---|---|
| `app/api.py` | 极简 HTTP 客户端（标准库 `urllib`，不引第三方）：POST/GET + JSON + 超时 + 统一解析 `AjaxResult`；区分"网络不通"和"服务器拒绝"两类错误 |
| `app/update.py` | 取下载列表 → 归一化版本号 → 比大小 → 给出 `UpdateInfo`（最新版 / 是否落后 / 下载地址 / 备注） |
| `app/report.py` | 组装诊断信息（应用版本、库版本、系统、Python、界面语言、主题、CLI 路径）→ **脱敏** → 截取日志尾部 → 提交 → 记下发出去的编号与数据码 |
| `app/ui/update_dialog.py` `app/ui/report_dialog.py` | 两个对话框：检查结果、反馈表单（可预览将要发送的内容） |

### 3.1 隐私（脱敏规则）

诊断信息**绝不能**把用户目录、存档路径、世界名、项目名带出去：

- 家目录 → `~`；`C:\Users\<名字>` 同样替换；
- 其它绝对路径只保留最后两级（`…/saves/base` 这种）；
- 不收集：存档/项目名字、区块坐标、素材包内容、文件清单；
- 日志尾部按同一规则过一遍再发出。

界面里会明确写出"将发送什么"，并且**发送前可以取消**。

### 3.2 失败与频率

- 检查更新：失败**静默**（离线、服务器 502 都不打扰用户），启动时最多每天一次
  （配置里记 `last_update_check`），手动点永远会真的查；
- 反馈提交：失败要明确说（网络不通 / 服务器拒绝 / 内容超长），并给出本机日志路径，
  方便用户直接发邮件；
- 超时：连接 3 秒、读取 8 秒。

## 4. 还需要服务端配合的两件事（按优先级）

1. `module` 加 `app`（一行 `Set.of(...)`），后台能区分来源；
2. 反馈加 `diagnostics`（TEXT，≤20 KB）——之后客户端把日志改走这个字段，
   不用再挤 `description`；
3. 更新接口补 `notes` / `min_version`（强制更新、更新日志）；
4. （可选）公开上传接口 + 限流，用来收完整日志包。
