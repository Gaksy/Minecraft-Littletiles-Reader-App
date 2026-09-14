"""English (en). 键 = 简体中文原文，值 = 译文。"""

STRINGS = {
    # ---- 菜单 ----
    "素材(&M)": "Assets(&M)",
    "材质管理": "Material manager",
    "区块选择说明": "Chunk selection help",
    "输出(&O)": "Output(&O)",
    "设置默认输出目录": "Set default output folder",
    "恢复默认输出目录": "Reset default output folder",
    "打开输出目录": "Open output folder",
    "清空日志窗口": "Clear log",
    "视图(&V)": "View(&V)",
    "语言": "Language",
    "切换到浅色主题": "Switch to light theme",
    "切换到深色主题": "Switch to dark theme",
    "应用(&A)": "App(&A)",
    "清空所有数据": "Clear all data",
    "帮助(&H)": "Help(&H)",
    "关于": "About",
    # ---- 启动界面 ----
    "要做什么？": "What would you like to do?",
    "导出 SNBT\n（结构文件 / 粘贴文本）": "Export SNBT\n(structure file / pasted text)",
    "导出存档\n（选区块导出 OBJ）": "Export from save\n(pick chunks, export OBJ)",
    "上面两个是快速导出：不绑定项目、不记录历史。想留记录、留素材副本、以后还能查「哪块导过」，就用下面的项目。": (
        "The two buttons above are quick exports: no project, no history. "
        "Use a project below if you want export records, asset copies, and "
        "\"which chunk did I export?\" later."
    ),
    "（未设置）": "(not set)",
    "已配置": "configured",
    "（不可用，导出时会要求重新选择）%s": "(unavailable; you will be asked to pick again) %s",
    "素材包: %s    模型输出目录: %s%s    CLI: %s": (
        "Assets: %s    Output folder: %s%s    CLI: %s"
    ),
    # ---- 项目列表 ----
    "项目": "Projects",
    "新建项目": "New project",
    "添加已有项目": "Add existing project",
    "刷新": "Refresh",
    "还没有项目。新建一个，或把已有的项目目录添加进来。": (
        "No projects yet. Create one, or add an existing project folder."
    ),
    "共 %d 个%s": "%d project(s)%s",
    "（%d 个不可用）": " (%d unavailable)",
    "重新定位": "Relocate",
    "删除项目": "Delete project",
    "从列表移除，或者连同项目目录一起删除": (
        "Remove from the list, or delete the project folder as well"
    ),
    "项目不可用": "Project unavailable",
    "读不到 project.json——目录可能被搬走或删掉了。": (
        "Cannot read project.json — the folder may have been moved or deleted."
    ),
    "未命名项目": "Untitled project",
    "（没有描述）": "(no description)",
    "无封面": "No cover",
    "删除": "Delete",
    "取消": "Cancel",
    "确定": "OK",
    "要删除「%s」吗？": "Delete \"%s\"?",
    "仅从项目列表移除（磁盘上的目录保留）": (
        "Remove from the project list only (the folder stays on disk)"
    ),
    "删除项目目录（释放约 %s）": "Delete the project folder (frees about %s)",
    "删除项目目录（这个目录已经不在磁盘上了）": (
        "Delete the project folder (it is no longer on disk)"
    ),
    "我确认永久删除这个目录：素材副本、贴图库、导出产物、历史记录都会一起没有": (
        "I understand this permanently deletes the folder: asset copies, "
        "texture library, exports and history all go with it"
    ),
    "目录不在了，只能把这条登记从列表里删掉。": (
        "The folder is gone, so the entry can only be removed from the list."
    ),
    # ---- 导出对话框 ----
    "导出存档模型": "Export model from save",
    "存档": "Save",
    "存档根目录（含 level.dat 的那个文件夹）": (
        "Save folder (the one containing level.dat)"
    ),
    "选择文件夹": "Choose folder",
    "选择存档根目录": "Choose the save folder",
    "维度": "Dimension",
    "区块选择": "Chunk selection",
    "单区块": "Single chunk",
    "区块范围": "Chunk range",
    "中心 + 半径": "Center + radius",
    "主世界": "Overworld",
    "下界": "Nether",
    "末地": "The End",
    "中心 / 单块 x": "Center / single x",
    "中心 / 单块 z": "Center / single z",
    "半径 r": "Radius r",
    "范围起点 x1": "Range from x1",
    "范围起点 z1": "Range from z1",
    "范围终点 x2": "Range to x2",
    "范围终点 z2": "Range to z2",
    "选项": "Options",
    "同时导出普通方块": "Also export plain blocks",
    "剔除被相邻方块挡住的面": "Cull faces hidden by neighbours",
    "把模型中心移到原点": "Move the model center to the origin",
    "再把最长边缩放到 1 个单位（会改变真实尺寸）": (
        "Then scale the longest edge to 1 unit (changes the real size)"
    ),
    "区块概览：%d × %d%s": "Chunk overview: %d × %d%s",
    "（范围太大，图上只画了中间 %d × %d，其余靠拖动查看）": (
        " (range too large: only the middle %d × %d is drawn, drag to see the rest)"
    ),
    "灰 = 从未导出　绿 = 已导出且存档未变　黄 = 已导出但之后存档变过　黄框 = 本次范围": (
        "grey = never exported　green = exported, save unchanged　"
        "yellow = exported, save changed since　yellow frame = this selection"
    ),
    "黄框 = 本次范围（快速导出没有导出记录，不显示“导过没有”）": (
        "yellow frame = this selection (quick export keeps no records, "
        "so \"already exported?\" is unknown)"
    ),
    "把鼠标停在格子上看这一块的坐标与状态。": (
        "Hover a cell to see that chunk's coordinates and state."
    ),
    "本次：共 %d 个区块　x %d … %d　z %d … %d（%d × %d）": (
        "This export: %d chunk(s)　x %d … %d　z %d … %d (%d × %d)"
    ),
    "区块 (%d, %d)：%s": "Chunk (%d, %d): %s",
    "区块 (%d, %d)": "Chunk (%d, %d)",
    "状态：%s": "State: %s",
    "区域文件：r.%d.%d.mca": "Region file: r.%d.%d.mca",
    "这一块还没有导出过。": "This chunk has never been exported.",
    "在左边的概览图上点一个区块，这里显示它的详情。": (
        "Click a chunk in the overview to see its details here."
    ),
    "未导出": "not exported",
    "已导出": "exported",
    "可能已过期": "possibly outdated",
    # ---- 导出面板 ----
    "打包成 zip": "Pack as zip",
    "把模型、MTL 与这次用到的贴图收成一个 zip（放在产物目录里），拷贝到别处也能直接用": (
        "Collect the model, MTL and textures this export uses into a zip "
        "(written next to the output) so it can be used anywhere"
    ),
    "导出日志会显示在这里": "The export log shows up here",
    "解析": "Parse",
    "建网格": "Build mesh",
    "写出文件": "Write files",
    "普通方块": "Plain blocks",
    "剔除遮挡面": "Cull hidden faces",
    "居中": "Center",
    "单位缩放": "Unit scale",
    "将清空 %d 类，释放约 %s。": "Will clear %d category(ies), freeing about %s.",
    "清掉应用自己的数据，回到刚装好的状态": (
        "Clear the app's own data and go back to a fresh install"
    ),
    "清空": "Clear",
    "项目目录不会被删除（包括里面的素材副本、贴图库、导出产物与历史记录）。\n要删项目，用项目卡片上的「删除项目」。": (
        "Project folders are never deleted (including their asset copies, texture "
        "library, exports and history).\nTo delete a project, use \"Delete project\" "
        "on its card."
    ),

    # ---- 清空所有数据（分类名与说明）----
    '设置与项目登记': 'Settings and project registry',
    '默认输出目录、最近打开过的存档/结构、界面偏好、项目列表': 'Default output folder, recent saves/structures, UI preferences, project list',
    '素材库': 'Material library',
    '导入的材质包 / 模组、解包结果、素材组合缓存': 'Imported packs / mods, extracted files, composed asset cache',
    '导出产物与临时文件': 'Exports and temp files',
    '快速导出的 outputs/、导出与粘贴用的 tmp/': 'outputs/ of quick exports, tmp/ used by exports and pasting',
    '会话日志': 'Session logs',
    'logs/ 下按启动时间切分的日志文件': 'log files under logs/, one per app start',

    # ---- 通用弹窗按钮与语言菜单 ----
    '确定': 'OK',
    '取消': 'Cancel',
    '关闭': 'Close',
    '语言': 'Language',
    '界面语言已切换为 %s，重启应用后生效。': 'Interface language is now %s; restart the app to apply.',
    '跟随系统': 'Follow system',

    # ---- 存档目录检查 ----
    '还没有选择存档目录。': 'No save folder selected yet.',
    '这个路径不存在，或者不是目录。': 'That path does not exist or is not a folder.',
    '找到 %s/（%d 个 .mca）%s': 'Found %s/ (%d .mca)%s',
    '，含 level.dat': ', with level.dat',
    '这里像是 %s/ 目录本身，不是存档根目录。': 'This looks like the %s/ folder itself, not the save root.',
    '往上退一层选：%s': 'Go one level up: %s',
    '这个目录里没有直接的存档，但里面有 %d 个像存档的文件夹。': 'No save here, but %d subfolder(s) look like saves.',
    '大概想选的是：%s': 'You probably want: %s',
    '有 level.dat，但 %s/ 里没有 .mca 文件。': 'level.dat exists, but there are no .mca files in %s/.',
    '这个存档可能还没生成过地图，或者维度选错了。': 'The world may not have generated a map yet, or the dimension is wrong.',
    '这里既没有 level.dat，也没有 %s/。': 'Neither level.dat nor %s/ is here.',
    '存档根目录是含 level.dat 与 region/ 的那一层。': 'The save folder is the one containing level.dat and region/.',

    # ---- 存档检查行的前缀（中文用全角叹号，其它语言用半角）----
    "！": "!",

    # ---- 项目界面 / 关于 / 概览图 / 模式示意图 ----
    '快速导出': 'Quick export',
    '导出概览': 'Export overview',
    '维度': 'Dimension',
    '共 %d 个区块\u3000范围 %d × %d%s': '%d chunk(s)\u3000range %d × %d%s',
    '（太大，只画中间 %d × %d）': ' (too large: only the middle %d × %d is drawn)',
    '灰 = 没导过\u3000绿 = 已导出且存档未变\u3000黄 = 已导出但之后存档变过': 'grey = not exported\u3000green = exported, save unchanged\u3000yellow = exported, save changed since',
    '还没有导出记录': 'No exports yet',
    '这个项目还没有导出记录。导出一次之后，这里会画出导过哪些区块。': 'This project has no exports yet. After one export, this map shows which chunks were exported.',
    '把鼠标停在格子上看这一块的坐标与状态。': "Hover a cell to see that chunk's coordinates and state.",
    '在左边的概览图上点一个区块，这里显示它的详情。': 'Click a chunk in the overview to see its details here.',
    '区块 (%d, %d)：%s': 'Chunk (%d, %d): %s',
    '区块 (%d, %d)\n状态：没导过\n\n这个项目没有这一块的记录。': 'Chunk (%d, %d)\nState: never exported\n\nThis project has no record for it.',
    '区块 (%d, %d)': 'Chunk (%d, %d)',
    '状态：%s': 'State: %s',
    '导出于 %s': 'Exported at %s',
    '维度：%s': 'Dimension: %s',
    '面数：%d': 'Faces: %d',
    '产物：%s': 'Output: %s',
    '记录：%s': 'Record: %s',
    '界面版本：%s\n库版本：%s\n\n': 'App version: %s\nLibrary version: %s\n\n',
    '提交：%s\n\n': 'Commit: %s\n\n',
    '会话日志：\n%s\n\n': 'Session log:\n%s\n\n',
    '素材来自本机游戏与资源包，本工具只读取、不附带、不分发。': 'Assets come from the local game and resource packs; this tool only reads, never bundles or redistributes.',
    '（没问到库版本）': '(library version unknown)',
    '（未启用日志）': '(logging disabled)',
    '没有删除': 'Nothing deleted',
    '这个目录里没有 project.json，不像是项目目录，所以没有删除任何东西（登记也保留着）：\n%s\n\n如果只是不想再看到它，选「仅从项目列表移除」。': 'There is no project.json here, so this does not look like a project folder and nothing was deleted (the list entry is kept too):\n%s\n\nIf you only want it out of the list, choose "Remove from the project list only".',
    '删除失败': 'Delete failed',
    '输入一个区块坐标 (x, z)，只导出这一块。': 'Enter one chunk (x, z); only that chunk is exported.',
    '输入起点 (x1, z1) 与终点 (x2, z2)，导出这个矩形里的所有区块。': 'Enter the corners (x1, z1) and (x2, z2); every chunk in that rectangle is exported.',
    '输入中心 (x, z) 与半径 r，导出中心周围 (2r+1)² 个区块（亮黄框是中心）。': 'Enter the center (x, z) and radius r; (2r+1)² chunks around it are exported (yellow frame = center).',

    # ---- 新建项目向导 ----
    '这个项目叫什么？': 'What is this project called?',
    '名称与简介只影响界面显示，随时可以在「项目配置」里改。': 'Name and description only affect what you see; you can change them later in "Project settings".',
    '项目名（必填）': 'Project name (required)',
    '例如：地铁站 · 站台吊顶': 'e.g. Subway · platform ceiling',
    '简介': 'Description',
    '这个项目是做什么的（可以留空）': 'What is this project for? (optional)',
    '存档在哪？': 'Where is the save?',
    '存档目录是必须的：项目模式的导出默认就从这里取区块。': 'A save folder is required: project exports take their chunks from here by default.',
    '存档目录（必填）': 'Save folder (required)',
    '封面（可选）': 'Cover image (optional)',
    '选择封面图片': 'Choose cover image',
    '清除封面': 'Clear cover',
    '存档目录是必填项。': 'The save folder is required.',
    '还差一步': 'One more thing',
    '请先填项目名。': 'Please enter a project name first.',
    '存档目录是必须的，请先选一个。': 'The save folder is required — please choose one.',
    '这个路径不存在，或者不是目录：\n%s': 'That path does not exist or is not a folder:\n%s',
    '确认存档目录': 'Confirm the save folder',
    '这个目录看起来不像是存档根目录（没有 level.dat 或 region/）。\n\n仍然用它作为本项目的默认存档位置吗？': "This folder does not look like a save root (no level.dat or region/).\n\nUse it as this project's default save folder anyway?",
    '图片 (*.png *.jpg *.jpeg *.bmp);;所有文件 (*)': 'Images (*.png *.jpg *.jpeg *.bmp);;All files (*)',
    '上一步': '< Back',
    '下一步': 'Next >',
    '完成': 'Finish',
    '选择项目目录（可以在对话框里新建一个文件夹）': 'Choose the project folder (you can create one here)',
    '建不了项目': 'Could not create the project',

    # ---- 项目模式：存档位置锁定 ----
    '存档位置来自项目配置，要改请用项目界面上的「项目配置」。': 'The save folder comes from the project settings; change it with "Project settings" in the project window.',

    # ---- 导出对话框：本次范围摘要 ----
    '本次：共 %d 个区块\u3000x %d … %d\u3000z %d … %d\n（右图只说明三种模式的取法，范围以上面的输入为准）': 'This export: %d chunk(s)\u3000x %d … %d\u3000z %d … %d\n(The illustration only explains the three modes; the range above is what counts.)',

    # ---- 快速导出时那块网格的说明 ----
    '（项目模式下这里会显示每个区块导出过没有）': '(In project mode this shows which chunks were already exported.)',
}
