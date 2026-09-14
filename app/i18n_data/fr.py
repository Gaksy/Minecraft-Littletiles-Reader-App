"""Français（fr）。"""

STRINGS = {
    # ---- Menus ----
    "素材(&M)": "Ressources(&M)",
    "材质管理": "Gestion des matériaux",
    "区块选择说明": "Aide sur le choix des chunks",
    "输出(&O)": "Sortie(&O)",
    "设置默认输出目录": "Définir le dossier de sortie par défaut",
    "恢复默认输出目录": "Rétablir le dossier de sortie par défaut",
    "打开输出目录": "Ouvrir le dossier de sortie",
    "清空日志窗口": "Vider le journal",
    "视图(&V)": "Affichage(&V)",
    "语言": "Langue",
    "切换到浅色主题": "Passer au thème clair",
    "切换到深色主题": "Passer au thème sombre",
    "应用(&A)": "Application(&A)",
    "清空所有数据": "Effacer toutes les données",
    "帮助(&H)": "Aide(&H)",
    "关于": "À propos",
    # ---- Écran d'accueil ----
    "要做什么？": "Que voulez-vous faire ?",
    "导出 SNBT\n（结构文件 / 粘贴文本）": "Exporter du SNBT\n(fichier de structure / texte collé)",
    "导出存档\n（选区块导出 OBJ）": "Exporter depuis une sauvegarde\n(choisir des chunks, OBJ)",
    "上面两个是快速导出：不绑定项目、不记录历史。想留记录、留素材副本、以后还能查「哪块导过」，就用下面的项目。": (
        "Les deux boutons ci-dessus sont des exports rapides : aucun projet, aucun historique. "
        "Pour garder l'historique, une copie des ressources et savoir « quel chunk a été exporté », "
        "utilisez un projet ci-dessous."
    ),
    "（未设置）": "(non défini)",
    "已配置": "configuré",
    "（不可用，导出时会要求重新选择）%s": "(indisponible, il faudra le resélectionner à l'export) %s",
    "素材包: %s    模型输出目录: %s%s    CLI: %s": (
        "Pack de ressources : %s    Dossier de sortie : %s%s    CLI : %s"
    ),
    # ---- Liste des projets ----
    "项目": "Projets",
    "新建项目": "Nouveau projet",
    "添加已有项目": "Ajouter un projet existant",
    "刷新": "Actualiser",
    "还没有项目。新建一个，或把已有的项目目录添加进来。": (
        "Aucun projet. Créez-en un ou ajoutez un dossier de projet existant."
    ),
    "共 %d 个%s": "%d au total%s",
    "（%d 个不可用）": " (%d indisponible(s))",
    "重新定位": "Relocaliser",
    "删除项目": "Supprimer le projet",
    "从列表移除，或者连同项目目录一起删除": (
        "Retirer de la liste, ou supprimer aussi le dossier du projet"
    ),
    "项目不可用": "Projet indisponible",
    "读不到 project.json——目录可能被搬走或删掉了。": (
        "Impossible de lire project.json — le dossier a peut-être été déplacé ou supprimé."
    ),
    "未命名项目": "Projet sans nom",
    "（没有描述）": "(aucune description)",
    "无封面": "Pas de couverture",
    "删除": "Supprimer",
    "取消": "Annuler",
    "确定": "OK",
    "要删除「%s」吗？": "Supprimer « %s » ?",
    "仅从项目列表移除（磁盘上的目录保留）": (
        "Retirer seulement de la liste (le dossier reste sur le disque)"
    ),
    "删除项目目录（释放约 %s）": "Supprimer le dossier du projet (libère environ %s)",
    "删除项目目录（这个目录已经不在磁盘上了）": (
        "Supprimer le dossier du projet (il n'existe plus sur le disque)"
    ),
    "我确认永久删除这个目录：素材副本、贴图库、导出产物、历史记录都会一起没有": (
        "Je confirme la suppression définitive : copies des ressources, "
        "bibliothèque de textures, exports et historique disparaissent aussi"
    ),
    "目录不在了，只能把这条登记从列表里删掉。": (
        "Le dossier n'existe plus ; seule l'entrée de la liste peut être retirée."
    ),
    # ---- Boîte d'export ----
    "导出存档模型": "Exporter le modèle depuis une sauvegarde",
    "存档": "Sauvegarde",
    "存档根目录（含 level.dat 的那个文件夹）": (
        "Dossier de sauvegarde (celui qui contient level.dat)"
    ),
    "选择文件夹": "Choisir un dossier",
    "选择存档根目录": "Choisir le dossier de sauvegarde",
    "维度": "Dimension",
    "区块选择": "Choix des chunks",
    "单区块": "Un seul chunk",
    "区块范围": "Plage de chunks",
    "中心 + 半径": "Centre + rayon",
    "主世界": "Overworld",
    "下界": "Nether",
    "末地": "End",
    "中心 / 单块 x": "Centre / unité x",
    "中心 / 单块 z": "Centre / unité z",
    "半径 r": "Rayon r",
    "范围起点 x1": "Début x1",
    "范围起点 z1": "Début z1",
    "范围终点 x2": "Fin x2",
    "范围终点 z2": "Fin z2",
    "选项": "Options",
    "同时导出普通方块": "Exporter aussi les blocs normaux",
    "剔除被相邻方块挡住的面": "Supprimer les faces cachées par les voisins",
    "把模型中心移到原点": "Placer le centre du modèle à l'origine",
    "再把最长边缩放到 1 个单位（会改变真实尺寸）": (
        "Puis mettre l'arête la plus longue à 1 unité (modifie la taille réelle)"
    ),
    "区块概览：%d × %d%s": "Aperçu des chunks : %d × %d%s",
    "（范围太大，图上只画了中间 %d × %d，其余靠拖动查看）": (
        " (plage trop grande : seul le centre %d × %d est dessiné, faites glisser pour voir le reste)"
    ),
    "灰 = 从未导出　绿 = 已导出且存档未变　黄 = 已导出但之后存档变过　黄框 = 本次范围": (
        "gris = jamais exporté　vert = exporté, sauvegarde inchangée　"
        "jaune = exporté puis sauvegarde modifiée　cadre jaune = cette plage"
    ),
    "黄框 = 本次范围（快速导出没有导出记录，不显示“导过没有”）": (
        "cadre jaune = cette plage (l'export rapide ne tient pas d'historique, "
        "donc « déjà exporté ? » reste inconnu)"
    ),
    "把鼠标停在格子上看这一块的坐标与状态。": (
        "Survolez une case pour voir les coordonnées et l'état du chunk."
    ),
    "本次：共 %d 个区块　x %d … %d　z %d … %d（%d × %d）": (
        "Cet export : %d chunk(s)　x %d … %d　z %d … %d (%d × %d)"
    ),
    "区块 (%d, %d)：%s": "Chunk (%d, %d) : %s",
    "区块 (%d, %d)": "Chunk (%d, %d)",
    "状态：%s": "État : %s",
    "区域文件：r.%d.%d.mca": "Fichier de région : r.%d.%d.mca",
    "这一块还没有导出过。": "Ce chunk n'a jamais été exporté.",
    "在左边的概览图上点一个区块，这里显示它的详情。": (
        "Cliquez sur un chunk dans l'aperçu pour voir ses détails ici."
    ),
    "未导出": "non exporté",
    "已导出": "exporté",
    "可能已过期": "peut-être obsolète",
    # ---- Panneau d'export ----
    "打包成 zip": "Empaqueter en zip",
    "把模型、MTL 与这次用到的贴图收成一个 zip（放在产物目录里），拷贝到别处也能直接用": (
        "Regroupe le modèle, le MTL et les textures utilisées dans un zip "
        "(écrit dans le dossier de sortie) ; utilisable tel quel ailleurs"
    ),
    "导出日志会显示在这里": "Le journal d'export s'affiche ici",
    "解析": "Analyse",
    "建网格": "Maillage",
    "写出文件": "Écriture",
    "普通方块": "Blocs normaux",
    "剔除遮挡面": "Retirer les faces cachées",
    "居中": "Centrer",
    "单位缩放": "Échelle unitaire",

    # ---- 清空所有数据（分类名与说明）----
    '设置与项目登记': 'Réglages et liste des projets',
    '默认输出目录、最近打开过的存档/结构、界面偏好、项目列表': "Dossier de sortie par défaut, sauvegardes/structures récentes, préférences d'interface, liste des projets",
    '素材库': 'Bibliothèque de ressources',
    '导入的材质包 / 模组、解包结果、素材组合缓存': 'Packs / mods importés, fichiers extraits, cache de composition',
    '导出产物与临时文件': 'Exports et fichiers temporaires',
    '快速导出的 outputs/、导出与粘贴用的 tmp/': "outputs/ des exports rapides, tmp/ pour l'export et le collage",
    '会话日志': 'Journaux de session',
    'logs/ 下按启动时间切分的日志文件': 'fichiers journaux dans logs/, un par démarrage',

    # ---- 通用弹窗按钮与语言菜单 ----
    '确定': 'OK',
    '取消': 'Annuler',
    '关闭': 'Fermer',
    '界面语言已切换为 %s，重启应用后生效。': "Langue de l'interface : %s. Redémarrez l'application pour l'appliquer.",
    '跟随系统': 'Suivre le système',

    # ---- 存档目录检查 ----
    '还没有选择存档目录。': 'Aucun dossier de sauvegarde sélectionné.',
    '这个路径不存在，或者不是目录。': "Ce chemin n'existe pas ou n'est pas un dossier.",
    '找到 %s/（%d 个 .mca）%s': '%s/ trouvé (%d .mca)%s',
    '，含 level.dat': ', avec level.dat',
    '这里像是 %s/ 目录本身，不是存档根目录。': 'Ceci semble être le dossier %s/ lui-même, pas la racine de la sauvegarde.',
    '往上退一层选：%s': "Remontez d'un niveau : %s",
    '这个目录里没有直接的存档，但里面有 %d 个像存档的文件夹。': 'Pas de sauvegarde ici, mais %d sous-dossier(s) ressemblent à des sauvegardes.',
    '大概想选的是：%s': 'Vous voulez probablement : %s',
    '有 level.dat，但 %s/ 里没有 .mca 文件。': 'level.dat présent, mais aucun .mca dans %s/.',
    '这个存档可能还没生成过地图，或者维度选错了。': "La carte n'est peut-être pas encore générée, ou la dimension est incorrecte.",
    '这里既没有 level.dat，也没有 %s/。': 'Ni level.dat ni %s/ ici.',
    '存档根目录是含 level.dat 与 region/ 的那一层。': 'La racine de la sauvegarde contient level.dat et region/.',

    # ---- 存档检查行的前缀（中文用全角叹号，其它语言用半角）----
    "！": "!",

    # ---- 项目界面 / 关于 / 概览图 / 模式示意图 ----
    '快速导出': 'Export rapide',
    '导出概览': 'Aperçu des exports',
    '共 %d 个区块\u3000范围 %d × %d%s': '%d chunk(s)\u3000plage %d × %d%s',
    '（太大，只画中间 %d × %d）': ' (trop grand : seul le centre %d × %d est dessiné)',
    '灰 = 没导过\u3000绿 = 已导出且存档未变\u3000黄 = 已导出但之后存档变过': 'gris = jamais exporté\u3000vert = exporté, sauvegarde inchangée\u3000jaune = exporté puis sauvegarde modifiée',
    '还没有导出记录': 'Aucun export',
    '这个项目还没有导出记录。导出一次之后，这里会画出导过哪些区块。': "Ce projet n'a pas encore d'export. Après un export, cette carte montrera quels chunks ont été exportés.",
    '区块 (%d, %d)\n状态：没导过\n\n这个项目没有这一块的记录。': "Chunk (%d, %d)\nÉtat : jamais exporté\n\nCe projet n'a aucun enregistrement ici.",
    '导出于 %s': 'Exporté le %s',
    '维度：%s': 'Dimension : %s',
    '面数：%d': 'Faces : %d',
    '产物：%s': 'Sortie : %s',
    '记录：%s': 'Enregistrement : %s',
    '界面版本：%s\n库版本：%s\n\n': "Version de l'app : %s\nVersion de la bibliothèque : %s\n\n",
    '提交：%s\n\n': 'Commit : %s\n\n',
    '会话日志：\n%s\n\n': 'Journal de session :\n%s\n\n',
    '素材来自本机游戏与资源包，本工具只读取、不附带、不分发。': 'Les ressources viennent du jeu et des packs locaux ; cet outil ne fait que lire, sans rien inclure ni redistribuer.',
    '（没问到库版本）': '(version de la bibliothèque inconnue)',
    '（未启用日志）': '(journalisation désactivée)',
    '没有删除': "Rien n'a été supprimé",
    '这个目录里没有 project.json，不像是项目目录，所以没有删除任何东西（登记也保留着）：\n%s\n\n如果只是不想再看到它，选「仅从项目列表移除」。': "Pas de project.json ici : ce dossier ne ressemble pas à un projet, donc rien n'a été supprimé (l'entrée de la liste reste) :\n%s\n\nPour le retirer seulement de la liste, choisissez « Retirer seulement de la liste ».",
    '删除失败': 'Échec de la suppression',
    '输入一个区块坐标 (x, z)，只导出这一块。': 'Saisissez un chunk (x, z) : seul celui-ci sera exporté.',
    '输入起点 (x1, z1) 与终点 (x2, z2)，导出这个矩形里的所有区块。': 'Saisissez les coins (x1, z1) et (x2, z2) : tous les chunks de ce rectangle seront exportés.',
    '输入中心 (x, z) 与半径 r，导出中心周围 (2r+1)² 个区块（亮黄框是中心）。': 'Saisissez le centre (x, z) et le rayon r : (2r+1)² chunks autour seront exportés (cadre jaune = centre).',

    # ---- 新建项目向导 ----
    '这个项目叫什么？': "Comment s'appelle ce projet ?",
    '名称与简介只影响界面显示，随时可以在「项目配置」里改。': "Le nom et la description ne servent qu'à l'affichage ; modifiables dans « Réglages du projet ».",
    '项目名（必填）': 'Nom du projet (obligatoire)',
    '例如：地铁站 · 站台吊顶': 'ex. : Métro · plafond du quai',
    '简介': 'Description',
    '这个项目是做什么的（可以留空）': 'À quoi sert ce projet ? (facultatif)',
    '存档在哪？': 'Où est la sauvegarde ?',
    '存档目录是必须的：项目模式的导出默认就从这里取区块。': 'Un dossier de sauvegarde est obligatoire : les exports de projet y prennent les chunks par défaut.',
    '存档目录（必填）': 'Dossier de sauvegarde (obligatoire)',
    '封面（可选）': 'Image de couverture (facultative)',
    '选择封面图片': 'Choisir une image',
    '清除封面': "Retirer l'image",
    '存档目录是必填项。': 'Le dossier de sauvegarde est obligatoire.',
    '还差一步': 'Encore une étape',
    '请先填项目名。': "Indiquez d'abord un nom de projet.",
    '存档目录是必须的，请先选一个。': 'Le dossier de sauvegarde est obligatoire — choisissez-en un.',
    '这个路径不存在，或者不是目录：\n%s': "Ce chemin n'existe pas ou n'est pas un dossier :\n%s",
    '确认存档目录': 'Confirmer le dossier de sauvegarde',
    '这个目录看起来不像是存档根目录（没有 level.dat 或 region/）。\n\n仍然用它作为本项目的默认存档位置吗？': "Ce dossier ne ressemble pas à une racine de sauvegarde (pas de level.dat ni region/).\n\nL'utiliser quand même comme dossier de sauvegarde par défaut ?",
    '图片 (*.png *.jpg *.jpeg *.bmp);;所有文件 (*)': 'Images (*.png *.jpg *.jpeg *.bmp);;Tous les fichiers (*)',
    '上一步': '< Précédent',
    '下一步': 'Suivant >',
    '完成': 'Terminer',
    '选择项目目录（可以在对话框里新建一个文件夹）': 'Choisir le dossier du projet (créable ici)',
    '建不了项目': 'Impossible de créer le projet',

    # ---- 项目模式：存档位置锁定 ----
    '存档位置来自项目配置，要改请用项目界面上的「项目配置」。': 'Le dossier de sauvegarde vient des réglages du projet ; modifiez-le via « Réglages du projet » dans la fenêtre du projet.',

    # ---- 导出对话框：本次范围摘要 ----
    '本次：共 %d 个区块\u3000x %d … %d\u3000z %d … %d\n（右图只说明三种模式的取法，范围以上面的输入为准）': "Cet export : %d chunk(s)\u3000x %d … %d\u3000z %d … %d\n(L'illustration n'explique que les trois modes ; la plage saisie ci-dessus fait foi.)",

    # ---- 快速导出时那块网格的说明 ----
    '（项目模式下这里会显示每个区块导出过没有）': '(En mode projet, ceci indique quels chunks ont déjà été exportés.)',
}
