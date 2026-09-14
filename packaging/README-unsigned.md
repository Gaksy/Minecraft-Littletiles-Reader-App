# 安装说明（macOS · 未签名版本）

这个版本**没有做 Apple 签名与公证**（签名要 Apple Developer 账号，每年 $99；
第一版先省掉）。macOS 因此会在你第一次打开时拦一下——**不是文件坏了**，
只是系统不认识这个开发者。下面任选一种方式通过即可，之后正常双击就能用。

## 方式一：右键打开（最简单）

1. 把 `LittleTilesReader.app` 拖进「应用程序」文件夹（别直接在下载目录里跑，
   否则数据目录会建在下载目录里）；
2. 在 Finder 里**右键点它 → 打开**；
3. 弹窗里再点一次「打开」。

之后再双击就是正常启动。

## 方式二：系统设置里放行

如果双击时提示"无法打开，因为 Apple 无法检查其是否包含恶意软件"：

1. 打开「系统设置 → 隐私与安全性」；
2. 拉到下面找到"已阻止使用 LittleTilesReader"；
3. 点「仍要打开」，再输入密码确认。

## 方式三：命令行去掉隔离标记（终端一行）

macOS 会给下载来的文件打 `com.apple.quarantine` 标记。去掉它等同于"我信任这个来源"：

```bash
# 把 .app 拖进终端会自动补全路径，或者手动写：
xattr -dr com.apple.quarantine /Applications/LittleTilesReader.app

# 想确认标记是否已清掉（没有输出就表示干净了）：
xattr /Applications/LittleTilesReader.app
```

## 方式四：自己给自己签名（可选）

ad-hoc 签名（不是身份签名，不花钱）有时能让系统少弹一次；如果你本机装了
Xcode 命令行工具，可以这样：

```bash
# 先去掉隔离标记，再本地 ad-hoc 签名（- 表示"不指定身份"）
xattr -dr com.apple.quarantine /Applications/LittleTilesReader.app
codesign --force --deep --sign - /Applications/LittleTilesReader.app

# 验一下签名（会打印 adhoc 与你的机器信息）
codesign -dv --verbose=2 /Applications/LittleTilesReader.app
```

> 自签名只在本机有效，**不能**帮你把它发给别人用——别人机器上还是会拦。
> 真要给别人用就得买开发者账号做正式签名 + 公证。

## 怎么确认拿到的是原版包

发布页会给出压缩包的 SHA-256。下载后核对：

```bash
shasum -a 256 ~/Downloads/LittleTilesReader-*.zip
# 与发布页那一行对比，一致才用
```

## 它会在哪儿写文件

默认**就在应用所在文件夹**（便携）：应用旁边会多出 `config/`（设置、项目登记）、
`logs/`（会话日志）、`outputs/`（导出产物）、`resources/`（导入的素材）、`tmp/`。
卸载 = 删掉应用文件夹（数据一起走）。

如果你把应用放进了 `/Applications`（系统目录、不可写），它会自动改用
`~/Library/Application Support/LittleTilesReader`，启动时日志里会写明。
想手动指定位置：设环境变量 `LTR_HOME=/你的目录` 再启动。
