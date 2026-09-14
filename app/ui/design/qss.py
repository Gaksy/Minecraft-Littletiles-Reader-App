"""由设计令牌生成全局 QSS（Qt 样式表）。

为什么用 QSS 而不是逐控件调色板：**跨平台一致**。Qt 的默认样式在 Windows /
macOS 上各不相同，用系统调色板拼出来的界面换台机器就变了；QSS 一把梭，
两端长得一样，而且能精确复刻网站的形态（直角、2px 描边、像素字体、
石头底 + 草绿 + 亮黄 hover）。

约定：
* 想强调的按钮给属性 `variant`：`primary` / `danger` / `ghost`（默认是普通按钮）；
* 标签用属性 `role`：`title` / `subtitle` / `hint` / `muted` / `mono`；
* 需要"卡片/面板"外观的容器给属性 `card="true"`。
"""

from __future__ import annotations

from .fonts import font_families_css
from .icons import icon_url
from .tokens import METRICS, Theme, theme_by_name


def build_stylesheet(theme: Theme | None = None) -> str:
    """把主题令牌渲染成一份完整 QSS。"""

    t = theme or theme_by_name("dark")
    m = METRICS
    families = font_families_css()
    check_icon = icon_url("check.png")
    check_rule = (
        "image: %s;" % check_icon if check_icon else "background-color: %s;" % t.on_accent
    )

    return f"""
/* ==========================================================================
   全局主题 · 与网站（mcpixel-craft-ui / inception.work）同一套设计语言
   主题：{t.name}   由 app/ui/design/qss.py 生成，改样式请改令牌
   ========================================================================== */

* {{
    font-family: {families};
    font-size: {m.font_body}px;
    letter-spacing: {m.letter_spacing}px;
}}

QWidget {{
    background-color: {t.page};
    color: {t.text_1};
}}

QMainWindow, QDialog, QWizard {{
    background-color: {t.page};
}}

QWidget:disabled {{
    color: {t.text_4};
}}

/* ---------- 文本层级 ---------- */

QLabel[role="title"] {{
    font-size: {m.font_title}px;
    font-weight: bold;
    color: {t.text_1};
}}

QLabel[role="subtitle"] {{
    font-size: {m.font_medium}px;
    font-weight: bold;
    color: {t.text_1};
}}

QLabel[role="hint"], QLabel[role="muted"] {{
    color: {t.text_3};
}}

QLabel[role="dim"] {{
    color: {t.text_4};
}}

QLabel[role="ok"] {{ color: {t.ok}; }}
QLabel[role="warn"] {{ color: {t.amber}; }}
QLabel[role="error"] {{ color: {t.danger}; }}

/* ---------- 面板 / 卡片 ---------- */

QWidget[card="true"], QFrame[card="true"], QGroupBox {{
    background-color: {t.sidebar};
    border: {m.border_width}px solid {t.border};
    border-radius: {m.radius}px;
}}

QGroupBox {{
    /* 分组标题要浮在框线上方，且不能贴着线：
       Qt 把边框画在"内容矩形"上，margin-top 这条空白就是标题的地盘，
       title 的 top 是"从这条带子的顶边往下数"——负值会顶出控件被裁掉（踩过）。
       所以：margin-top = 标题高度 + 间隙，top 只做几像素微调。 */
    margin-top: {m.gap_lg + 6}px;
    padding: {m.gap_md}px;
    font-weight: bold;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: {m.gap_md}px;
    top: {m.gap_xs}px;
    padding: 0 {m.gap_sm}px;
    color: {t.text_1};
}}

QFrame[role="separator"] {{
    background-color: {t.border};
    max-height: 1px;
    border: none;
}}

/* ---------- 按钮 ----------
   四种外观照搬组件库 McPixelButton 的变体：general（默认，浅灰像素按钮）、
   primary（蓝）、secondary（草绿，网站首页 CTA 用这个）、danger（橙）。
   都是 2px 实心描边 + 直角 + 粗体 + 竖直渐变，与网站一致。
   悬停时换成亮色填充 + 深色文字（组件库的 hover 行为）。 */

QPushButton, QToolButton {{
    background: {t.button_general_bg};
    color: {t.button_general_text};
    border: {m.border_width}px solid {t.button_general_border};
    border-radius: {m.radius}px;
    padding: 4px {m.gap_md}px;
    min-height: {m.control_height - 2 * m.border_width}px;
    font-size: 13px;
    font-weight: bold;
}}

QPushButton:hover, QToolButton:hover {{
    background: {t.button_general_hover_bg};
    color: {t.button_hover_text};
}}

QPushButton:pressed, QToolButton:pressed {{
    background: {t.button_general_hover_bg};
    color: {t.button_hover_text};
}}

QPushButton:disabled, QToolButton:disabled {{
    background: {t.surface};
    color: {t.text_4};
    border-color: {t.border_soft};
}}

QPushButton[variant="primary"] {{
    background: {t.button_primary_bg};
    border-color: {t.button_general_border};
    color: {t.button_general_text};
}}

QPushButton[variant="primary"]:hover {{
    background: {t.button_primary_hover_bg};
    color: {t.button_hover_text};
}}

QPushButton[variant="secondary"] {{
    background: {t.button_secondary_bg};
    border-color: {t.button_secondary_border};
    color: {t.button_secondary_text};
}}

QPushButton[variant="secondary"]:hover {{
    background: {t.button_secondary_hover_bg};
    color: {t.button_hover_text};
}}

QPushButton[variant="danger"] {{
    background: {t.button_danger_bg};
    border-color: {t.button_danger_border};
    color: {t.button_secondary_text};
}}

QPushButton[variant="danger"]:hover {{
    background: {t.button_danger_hover_bg};
    color: {t.button_hover_text};
}}

QPushButton[variant="ghost"] {{
    background: transparent;
    border-color: {t.border};
    color: {t.text_2};
}}

QPushButton[variant="ghost"]:hover {{
    background: {t.surface_2};
    border-color: {t.hover};
    color: {t.hover};
}}

QPushButton[size="small"] {{
    min-height: {m.button_small_height - 2 * m.border_width}px;
    font-size: {m.font_small}px;
    padding: 0 {m.gap_sm}px;
}}

QPushButton[size="large"] {{
    min-height: {m.button_large_height - 2 * m.border_width}px;
    font-size: {m.font_large}px;
}}

/* ---------- 输入类 ---------- */

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit,
QTextBrowser {{
    background-color: {t.surface};
    color: {t.text_1};
    border: {m.border_width}px solid {t.border};
    border-radius: {m.radius}px;
    padding: 4px {m.gap_sm}px;
    min-height: {m.control_height - 2 * m.border_width}px;
    selection-background-color: {t.accent};
    selection-color: {t.on_accent};
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus,
QPlainTextEdit:focus, QTextEdit:focus, QTextBrowser:focus {{
    border-color: {t.accent};
    background-color: {t.sidebar};
}}

QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled,
QPlainTextEdit:disabled, QTextEdit:disabled {{
    color: {t.text_4};
    border-color: {t.border_soft};
}}

QLineEdit[readOnly="true"] {{
    color: {t.text_3};
}}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 18px;
    border-left: {m.border_width}px solid {t.border};
    background-color: {t.surface_2};
}}

QComboBox::down-arrow {{
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {t.text_2};
}}

QComboBox QAbstractItemView {{
    background-color: {t.sidebar};
    color: {t.text_1};
    border: {m.border_width}px solid {t.border};
    selection-background-color: {t.accent};
    selection-color: {t.on_accent};
    outline: none;
}}

QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background-color: {t.surface_2};
    border-left: {m.border_width}px solid {t.border};
    width: 16px;
}}

QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid {t.text_2};
}}

QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {t.text_2};
}}

/* ---------- 勾选 / 单选 ---------- */

QCheckBox, QRadioButton {{
    spacing: {m.gap_sm}px;
    background: transparent;
}}

QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: {m.border_width}px solid {t.border};
    background-color: {t.surface};
}}

QRadioButton::indicator {{
    border-radius: 0;  /* 这套风格是直角，单选框也保持方的 */
}}

QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {t.hover};
}}

QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background-color: {t.accent};
    border-color: {t.accent_strong};
    {check_rule}
}}

QCheckBox:disabled, QRadioButton:disabled {{
    color: {t.text_4};
}}

/* ---------- 列表 / 表格 / 树 ---------- */

QListWidget, QListView, QTreeWidget, QTreeView, QTableWidget, QTableView {{
    background-color: {t.sidebar};
    alternate-background-color: {t.surface};
    color: {t.text_1};
    border: {m.border_width}px solid {t.border};
    border-radius: {m.radius}px;
    gridline-color: {t.border_soft};
    outline: none;
    selection-background-color: {t.accent};
    selection-color: {t.on_accent};
}}

QListWidget::item, QListView::item, QTreeWidget::item, QTreeView::item {{
    padding: {m.gap_xs}px {m.gap_sm}px;
    min-height: {m.control_height - m.border_width * 4}px;
}}

QListWidget::item:hover, QTreeWidget::item:hover, QTableWidget::item:hover {{
    background-color: {t.surface_2};
    color: {t.hover};
}}

QListWidget::item:selected, QTreeWidget::item:selected,
QTableWidget::item:selected, QTreeView::item:selected {{
    background-color: {t.accent};
    color: {t.on_accent};
}}

QHeaderView::section {{
    background-color: {t.surface_2};
    color: {t.text_2};
    border: none;
    border-right: {m.border_width}px solid {t.border};
    border-bottom: {m.border_width}px solid {t.border};
    padding: 4px {m.gap_sm}px;
    font-weight: bold;
}}

QTableCornerButton::section {{
    background-color: {t.surface_2};
    border: none;
}}

/* ---------- 标签页 ---------- */

QTabWidget::pane {{
    border: {m.border_width}px solid {t.border};
    background-color: {t.sidebar};
    top: -{m.border_width}px;
}}

QTabBar::tab {{
    background-color: {t.surface};
    color: {t.text_3};
    border: {m.border_width}px solid {t.border};
    border-bottom: none;
    padding: {m.gap_xs}px {m.gap_md}px;
    margin-right: 2px;
}}

QTabBar::tab:hover {{
    color: {t.hover};
}}

QTabBar::tab:selected {{
    background-color: {t.sidebar};
    color: {t.text_1};
    border-color: {t.accent};
}}

/* ---------- 滚动条 ---------- */

QScrollBar:vertical {{
    background: {t.surface};
    width: 12px;
    margin: 0;
    border: none;
}}

QScrollBar:horizontal {{
    background: {t.surface};
    height: 12px;
    margin: 0;
    border: none;
}}

QScrollBar::handle {{
    background: {t.surface_3};
    min-height: 24px;
    min-width: 24px;
    border: none;
}}

QScrollBar::handle:hover {{
    background: {t.accent};
}}

QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0; width: 0; border: none; background: none;
}}

QScrollBar::add-page, QScrollBar::sub-page {{
    background: none;
}}

QScrollArea {{
    border: none;
    background: transparent;
}}

/* ---------- 进度与滑块 ---------- */

QProgressBar {{
    background-color: {t.surface};
    border: {m.border_width}px solid {t.border};
    border-radius: {m.radius}px;
    color: {t.text_2};
    text-align: center;
    min-height: {m.control_height - 2 * m.border_width}px;
}}

QProgressBar::chunk {{
    background-color: {t.accent};
}}

QSlider::groove:horizontal {{
    height: 6px;
    background: {t.surface_2};
    border: none;
}}

QSlider::handle:horizontal {{
    background: {t.accent};
    border: {m.border_width}px solid {t.accent_strong};
    width: 12px;
    margin: -6px 0;
}}

/* ---------- 菜单 / 工具栏 / 状态栏 ---------- */

QMenuBar {{
    background-color: {t.header};
    color: {t.text_1};
    border-bottom: {m.border_width}px solid {t.border};
}}

QMenuBar::item {{
    padding: {m.gap_xs}px {m.gap_md}px;
    background: transparent;
}}

QMenuBar::item:selected {{
    background-color: {t.surface_2};
    color: {t.hover};
}}

QMenu {{
    background-color: {t.sidebar};
    color: {t.text_1};
    border: {m.border_width}px solid {t.border};
    padding: {m.gap_xs}px;
}}

QMenu::item {{
    padding: {m.gap_xs}px {m.gap_xl}px {m.gap_xs}px {m.gap_md}px;
}}

QMenu::item:selected {{
    background-color: {t.accent};
    color: {t.on_accent};
}}

QMenu::separator {{
    height: 1px;
    background: {t.border};
    margin: {m.gap_xs}px 0;
}}

QToolBar {{
    background-color: {t.sidebar};
    border: none;
    border-bottom: {m.border_width}px solid {t.border};
    spacing: {m.gap_sm}px;
    padding: {m.gap_xs}px;
}}

QStatusBar {{
    background-color: {t.sidebar};
    color: {t.text_3};
    border-top: {m.border_width}px solid {t.border};
}}

QStatusBar::item {{
    border: none;
}}

/* ---------- 提示 / 弹窗 ---------- */

QToolTip {{
    background-color: {t.sidebar};
    color: {t.text_1};
    border: {m.border_width}px solid {t.border};
    padding: {m.gap_xs}px {m.gap_sm}px;
}}

QSplitter::handle {{
    background-color: {t.border};
}}

QSplitter::handle:horizontal {{ width: {m.border_width}px; }}
QSplitter::handle:vertical {{ height: {m.border_width}px; }}

/* ---------- 分区标题（components.SectionTitle 用） ---------- */

QLabel[role="section"] {{
    font-size: {m.font_medium}px;
    font-weight: bold;
    color: {t.text_1};
    border-left: {m.gap_xs}px solid {t.accent};
    padding-left: {m.gap_sm}px;
}}

/* ---------- 状态标签（components.StatusChip 用） ---------- */

QLabel[chip="ok"] {{
    background-color: {t.ok_bg}; color: {t.ok};
    border: 1px solid {t.ok}; padding: 1px {m.gap_xs}px;
}}

QLabel[chip="warn"] {{
    background-color: {t.amber_bg}; color: {t.amber};
    border: 1px solid {t.amber}; padding: 1px {m.gap_xs}px;
}}

QLabel[chip="info"] {{
    background-color: {t.info_bg}; color: {t.info};
    border: 1px solid {t.info}; padding: 1px {m.gap_xs}px;
}}

QLabel[chip="error"] {{
    background-color: {t.danger_bg}; color: {t.danger};
    border: 1px solid {t.danger}; padding: 1px {m.gap_xs}px;
}}

QLabel[chip="muted"] {{
    background-color: {t.surface}; color: {t.text_3};
    border: 1px solid {t.border_soft}; padding: 1px {m.gap_xs}px;
}}

/* ---------- 纯展示控件（避免继承 QWidget 背景） ---------- */

QLabel, QCheckBox, QRadioButton, QToolTip {{
    background: transparent;
}}
""".strip() + "\n"


def stylesheet_for(theme_name: str) -> str:
    """按主题名（"dark" / "light"）生成 QSS。"""

    return build_stylesheet(theme_by_name(theme_name))
