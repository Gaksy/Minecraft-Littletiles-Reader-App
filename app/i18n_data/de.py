"""Deutsch（de）。"""

STRINGS = {
    # ---- Menüs ----
    "素材(&M)": "Material(&M)",
    "材质管理": "Materialverwaltung",
    "区块选择说明": "Hilfe zur Chunk-Auswahl",
    "输出(&O)": "Ausgabe(&O)",
    "设置默认输出目录": "Standard-Ausgabeordner festlegen",
    "恢复默认输出目录": "Standard-Ausgabeordner zurücksetzen",
    "打开输出目录": "Ausgabeordner öffnen",
    "清空日志窗口": "Protokoll leeren",
    "视图(&V)": "Ansicht(&V)",
    "语言": "Sprache",
    "切换到浅色主题": "Zum hellen Design wechseln",
    "切换到深色主题": "Zum dunklen Design wechseln",
    "应用(&A)": "App(&A)",
    "清空所有数据": "Alle Daten löschen",
    "帮助(&H)": "Hilfe(&H)",
    "关于": "Über",
    # ---- Startbildschirm ----
    "要做什么？": "Was möchtest du tun?",
    "导出 SNBT\n（结构文件 / 粘贴文本）": "SNBT exportieren\n(Strukturdatei / Text einfügen)",
    "导出存档\n（选区块导出 OBJ）": "Aus Spielstand exportieren\n(Chunks wählen, OBJ)",
    "上面两个是快速导出：不绑定项目、不记录历史。想留记录、留素材副本、以后还能查「哪块导过」，就用下面的项目。": (
        "Die beiden Knöpfe oben sind Schnellexporte: kein Projekt, keine Historie. "
        "Für Verlauf, Materialkopien und \"welcher Chunk wurde exportiert?\" "
        "nutze ein Projekt weiter unten."
    ),
    "（未设置）": "(nicht gesetzt)",
    "已配置": "konfiguriert",
    "（不可用，导出时会要求重新选择）%s": "(nicht verfügbar, wird beim Export neu gewählt) %s",
    "素材包: %s    模型输出目录: %s%s    CLI: %s": (
        "Materialpaket: %s    Ausgabeordner: %s%s    CLI: %s"
    ),
    # ---- Projektliste ----
    "项目": "Projekte",
    "新建项目": "Neues Projekt",
    "添加已有项目": "Vorhandenes Projekt hinzufügen",
    "刷新": "Aktualisieren",
    "还没有项目。新建一个，或把已有的项目目录添加进来。": (
        "Noch keine Projekte. Erstelle eines oder füge einen vorhandenen Ordner hinzu."
    ),
    "共 %d 个%s": "%d insgesamt%s",
    "（%d 个不可用）": " (%d nicht verfügbar)",
    "重新定位": "Neu verknüpfen",
    "删除项目": "Projekt löschen",
    "从列表移除，或者连同项目目录一起删除": (
        "Aus der Liste entfernen oder den Projektordner mitlöschen"
    ),
    "项目不可用": "Projekt nicht verfügbar",
    "读不到 project.json——目录可能被搬走或删掉了。": (
        "project.json ist nicht lesbar – der Ordner wurde vielleicht verschoben oder gelöscht."
    ),
    "未命名项目": "Unbenanntes Projekt",
    "（没有描述）": "(keine Beschreibung)",
    "无封面": "Kein Titelbild",
    "删除": "Löschen",
    "取消": "Abbrechen",
    "确定": "OK",
    "要删除「%s」吗？": "\"%s\" löschen?",
    "仅从项目列表移除（磁盘上的目录保留）": (
        "Nur aus der Liste entfernen (Ordner bleibt auf der Festplatte)"
    ),
    "删除项目目录（释放约 %s）": "Projektordner löschen (gibt ca. %s frei)",
    "删除项目目录（这个目录已经不在磁盘上了）": (
        "Projektordner löschen (liegt nicht mehr auf der Festplatte)"
    ),
    "我确认永久删除这个目录：素材副本、贴图库、导出产物、历史记录都会一起没有": (
        "Ich bestätige das endgültige Löschen: Materialkopien, Texturbibliothek, "
        "Exporte und Verlauf verschwinden mit"
    ),
    "目录不在了，只能把这条登记从列表里删掉。": (
        "Der Ordner ist weg; es kann nur der Eintrag entfernt werden."
    ),
    # ---- Exportdialog ----
    "导出存档模型": "Modell aus Spielstand exportieren",
    "存档": "Spielstand",
    "存档根目录（含 level.dat 的那个文件夹）": (
        "Spielstandordner (der mit level.dat)"
    ),
    "选择文件夹": "Ordner wählen",
    "选择存档根目录": "Spielstandordner wählen",
    "维度": "Dimension",
    "区块选择": "Chunk-Auswahl",
    "单区块": "Einzelner Chunk",
    "区块范围": "Chunk-Bereich",
    "中心 + 半径": "Mittelpunkt + Radius",
    "主世界": "Oberwelt",
    "下界": "Nether",
    "末地": "Ende",
    "中心 / 单块 x": "Mitte / einzeln x",
    "中心 / 单块 z": "Mitte / einzeln z",
    "半径 r": "Radius r",
    "范围起点 x1": "Bereich von x1",
    "范围起点 z1": "Bereich von z1",
    "范围终点 x2": "Bereich bis x2",
    "范围终点 z2": "Bereich bis z2",
    "选项": "Optionen",
    "同时导出普通方块": "Normale Blöcke mit exportieren",
    "剔除被相邻方块挡住的面": "Von Nachbarn verdeckte Flächen entfernen",
    "把模型中心移到原点": "Modellmitte in den Ursprung verschieben",
    "再把最长边缩放到 1 个单位（会改变真实尺寸）": (
        "Danach die längste Kante auf 1 Einheit skalieren (ändert die echte Größe)"
    ),
    "区块概览：%d × %d%s": "Chunk-Übersicht: %d × %d%s",
    "（范围太大，图上只画了中间 %d × %d，其余靠拖动查看）": (
        " (Bereich zu groß: nur die Mitte %d × %d wird gezeichnet, Rest per Ziehen)"
    ),
    "灰 = 从未导出　绿 = 已导出且存档未变　黄 = 已导出但之后存档变过　黄框 = 本次范围": (
        "grau = nie exportiert　grün = exportiert, Spielstand unverändert　"
        "gelb = exportiert, Spielstand danach geändert　gelber Rahmen = dieser Bereich"
    ),
    "黄框 = 本次范围（快速导出没有导出记录，不显示“导过没有”）": (
        "gelber Rahmen = dieser Bereich (Schnellexport führt keine Liste, "
        "daher kein \"schon exportiert?\")"
    ),
    "把鼠标停在格子上看这一块的坐标与状态。": (
        "Mit der Maus auf ein Feld zeigen: Koordinaten und Status."
    ),
    "本次：共 %d 个区块　x %d … %d　z %d … %d（%d × %d）": (
        "Dieser Export: %d Chunk(s)　x %d … %d　z %d … %d (%d × %d)"
    ),
    "区块 (%d, %d)：%s": "Chunk (%d, %d): %s",
    "区块 (%d, %d)": "Chunk (%d, %d)",
    "状态：%s": "Status: %s",
    "区域文件：r.%d.%d.mca": "Regiondatei: r.%d.%d.mca",
    "这一块还没有导出过。": "Dieser Chunk wurde noch nie exportiert.",
    "在左边的概览图上点一个区块，这里显示它的详情。": (
        "Klicke links in der Übersicht auf einen Chunk – hier erscheinen die Details."
    ),
    "未导出": "nicht exportiert",
    "已导出": "exportiert",
    "可能已过期": "evtl. veraltet",
    # ---- Exportleiste ----
    "打包成 zip": "Als zip bündeln",
    "把模型、MTL 与这次用到的贴图收成一个 zip（放在产物目录里），拷贝到别处也能直接用": (
        "Modell, MTL und die verwendeten Texturen in ein zip legen "
        "(im Ausgabeordner); anderswo direkt nutzbar"
    ),
    "导出日志会显示在这里": "Das Exportprotokoll erscheint hier",
    "解析": "Parsen",
    "建网格": "Mesh bauen",
    "写出文件": "Dateien schreiben",
    "普通方块": "Normale Blöcke",
    "剔除遮挡面": "Verdeckte Flächen entfernen",
    "居中": "Zentrieren",
    "单位缩放": "Einheitenskalierung",

    # ---- 清空所有数据（分类名与说明）----
    '设置与项目登记': 'Einstellungen und Projektliste',
    '默认输出目录、最近打开过的存档/结构、界面偏好、项目列表': 'Standard-Ausgabeordner, zuletzt geöffnete Spielstände/Strukturen, UI-Einstellungen, Projektliste',
    '素材库': 'Materialbibliothek',
    '导入的材质包 / 模组、解包结果、素材组合缓存': 'Importierte Pakete/Mods, entpackte Dateien, Material-Cache',
    '导出产物与临时文件': 'Exporte und temporäre Dateien',
    '快速导出的 outputs/、导出与粘贴用的 tmp/': 'outputs/ der Schnellexporte, tmp/ für Export und Einfügen',
    '会话日志': 'Sitzungsprotokolle',
    'logs/ 下按启动时间切分的日志文件': 'Protokolldateien unter logs/, pro Start getrennt',

    # ---- 通用弹窗按钮与语言菜单 ----
    '确定': 'OK',
    '取消': 'Abbrechen',
    '关闭': 'Schließen',
    '界面语言已切换为 %s，重启应用后生效。': 'Sprache auf %s gesetzt; nach einem Neustart aktiv.',
    '跟随系统': 'Systemeinstellung folgen',

    # ---- 存档目录检查 ----
    '还没有选择存档目录。': 'Noch kein Spielstandordner gewählt.',
    '这个路径不存在，或者不是目录。': 'Dieser Pfad existiert nicht oder ist kein Ordner.',
    '找到 %s/（%d 个 .mca）%s': '%s/ gefunden (%d .mca)%s',
    '，含 level.dat': ', mit level.dat',
    '这里像是 %s/ 目录本身，不是存档根目录。': 'Das sieht nach dem Ordner %s/ selbst aus, nicht nach dem Spielstand-Root.',
    '往上退一层选：%s': 'Eine Ebene höher wählen: %s',
    '这个目录里没有直接的存档，但里面有 %d 个像存档的文件夹。': 'Kein Spielstand direkt hier, aber %d Unterordner sehen wie Spielstände aus.',
    '大概想选的是：%s': 'Wahrscheinlich gemeint: %s',
    '有 level.dat，但 %s/ 里没有 .mca 文件。': 'level.dat ist da, aber keine .mca in %s/.',
    '这个存档可能还没生成过地图，或者维度选错了。': 'Vielleicht wurde noch keine Karte erzeugt, oder die Dimension stimmt nicht.',
    '这里既没有 level.dat，也没有 %s/。': 'Weder level.dat noch %s/ vorhanden.',
    '存档根目录是含 level.dat 与 region/ 的那一层。': 'Der Spielstandordner enthält level.dat und region/.',

    # ---- 存档检查行的前缀（中文用全角叹号，其它语言用半角）----
    "！": "!",
}
