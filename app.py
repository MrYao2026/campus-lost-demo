"""校园失物招领 —— Streamlit 前端。

运行方式：
    streamlit run app.py

物品数据统一来自 db.py；“我的”页面的志愿次数由数据库动态统计，
只有信用分暂时是演示常量。

部署到 Streamlit Community Cloud 时，如果服务器上没有 campus_lost.db，
应用启动会自动建表并写入 4 条演示数据（见 ensure_database()）。
"""

import html
import os
from datetime import datetime

import streamlit as st

import db

# ---------------------------------------------------------------- 云端启动自检
# Streamlit Community Cloud 每次部署都是一个全新的容器，
# 仓库里可能没有 campus_lost.db 文件。如果不先建库，
# 页面一打开就会报 "no such table: items"。
# 因此这里在渲染页面之前先检查数据库文件：
# 文件不存在时，自动建表并写入 4 条演示数据（相当于自动执行一次简化版 seed.py）。
# 注意：这段代码只做纯 Python / SQLite 操作，不能调用 st.* 组件，
# 否则会抢在 set_page_config 之前产生页面元素，导致配置生效异常。
BOOTSTRAP_ITEMS = [
    # (类型, 物品名称, 地点, 描述, 悬赏金额, 联系方式)
    ("lost", "黑色无线耳机", "图书馆", "在图书馆三楼自习区丢失，充电盒是白色的。", 30, "微信: demo_earphone"),
    ("lost", "校园卡", "第二食堂", "午饭时落在餐桌上，请捡到的同学联系我。", 0, "手机号: 13800000001"),
    ("found", "保温杯", "图书馆", "在图书馆一楼大厅捡到，银色保温杯。", 0, "微信: demo_cup"),
    ("found", "黑色书包", "教学楼A", "在教学楼A 305 教室捡到，里面有几本教材。", 0, "手机号: 13800000002"),
]


def ensure_database():
    """云端首次启动时自动建库并写入 4 条演示数据。

    执行条件：数据库文件不存在（本地已经有 campus_lost.db 时什么都不做，
    所以正常重启不会重复插入测试数据）。
    """
    if os.path.exists(db.DB_PATH):
        return

    # 建表。CREATE TABLE IF NOT EXISTS 本身是幂等的，重复调用也安全。
    db.init_db()

    # 插入演示数据，保证云端首页一打开就有内容，不会是一片空白。
    for item_type, title, location, description, bounty, contact in BOOTSTRAP_ITEMS:
        db.add_item(
            item_type=item_type,
            title=title,
            location=location,
            description=description,
            bounty=bounty,
            contact=contact,
        )


# 必须在任何页面渲染之前执行，这样后面的 load_items() 一定能读到表。
ensure_database()

# ---------------------------------------------------------------- 页面配置
st.set_page_config(
    page_title="校园寻物",
    page_icon="🔍",
    layout="centered",
    # 侧边栏默认展开。
    # 说明：Streamlit 会把“用户手动收起”这个选择记在浏览器的 localStorage 里，
    # 所以 "expanded" 能保证“首次访问时默认展开”；如果用户自己收起后又刷新，
    # 浏览器可能仍然保持收起——此时顶栏和展开箭头都可见，点一下就能打开，
    # 不会再出现“锁死打不开”的情况。
    # 如果希望桌面端彻底禁止收起（强制常开），可以把下面改成 "locked"。
    initial_sidebar_state="expanded",
)

# 隐藏 Streamlit 默认的主菜单、部署按钮和页脚，让页面更像独立 App。
#
# 【重要】绝对不要隐藏整个顶栏（header / [data-testid="stHeader"]）：
# 侧边栏的“展开箭头”就渲染在顶栏区域里，把 header 设成 visibility: hidden
# 会把箭头一起隐藏，用户一旦收起侧边栏，页面上就再也找不到打开它的入口了
# （这正是之前那个严重 Bug 的原因）。
#
# 安全做法：保留顶栏本身，只隐藏里面的具体按钮。
# 顶栏是白色的并不影响美观，导航能用才是第一位的。
hide_menu_style = """
        <style>
        /* 右上角的三点主菜单 */
        #MainMenu {visibility: hidden;}

        /* 右上角的 Deploy 按钮：新版用 data-testid，老版用 class，
           两个选择器都写上，升级 Streamlit 后也不会漏掉 */
        [data-testid="stAppDeployButton"],
        .stDeployButton {display: none;}

        /* 页脚的 “Made with Streamlit” */
        footer {visibility: hidden;}

        /* 双保险：显式保证侧边栏的展开/收起按钮可见、可点击。
           （新版是 stExpandSidebarButton，旧版是 stSidebarCollapseButton） */
        [data-testid="stExpandSidebarButton"],
        [data-testid="stSidebarCollapseButton"] {
            visibility: visible !important;
            pointer-events: auto !important;
        }
        </style>
        """
st.markdown(hide_menu_style, unsafe_allow_html=True)

# 类型、状态在界面上的中文名称。
TYPE_LABELS = {"lost": "寻物", "found": "招领"}
STATUS_META = {
    "open": ("进行中", "green"),
    "claimed": ("处理中", "orange"),
    "done": ("已完成", "gray"),
}

ALL_LOCATIONS = "全部"

# 发布表单里“类型”的选项 → 数据库中真正保存的值。
# 界面上显示中文方便用户理解，但数据库里只认 "lost" 和 "found"。
TYPE_CHOICES = {
    "寻物 (lost)": "lost",
    "招领 (found)": "found",
}

# 发布表单里可选的地点，要求是固定选项。
PUBLISH_LOCATIONS = ["图书馆", "第二食堂", "教学楼A", "操场", "宿舍区"]

# ---------------------------------------------------------------- “我的”页面配置
# 志愿记录次数不再写死，改为从数据库动态统计（见 db.get_volunteer_stats）。
# 目前还没有账号体系（单机演示），所以统计的是本机数据库里的全部记录。
CREDIT_SCORE = 92
CREDIT_THRESHOLD = 80

VOLUNTEER_EXPORT_NOTICE = (
    "Demo：此处生成《校园寻物志愿服务记录》，需经学校团委/学工审核后计入综测。"
)

# “我的发布”最多展示最近几条记录。
PROFILE_RECENT_LIMIT = 5

# 上传的图片统一放在项目根目录的 uploads/ 文件夹。
# 用 app.py 所在目录来拼接路径，这样从哪个目录启动程序都不会找错地方。
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")

# 启动时就确保 uploads/ 文件夹存在。
# 云端（Streamlit Community Cloud）是干净的容器，Git 仓库里通常不会提交空的
# uploads 目录，若不主动创建，上传图片时就会因为目录不存在而报错。
# 这等价于 os.makedirs("uploads", exist_ok=True)，只是改用绝对路径，
# 这样即使从别的目录启动应用，创建的也是 app.py 旁边的 uploads/。
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 页面路由名称。
# page 是“真正要显示的页面”，nav 只是侧边栏当前选中的项。
# 详情页不是侧边栏里的常规页面，所以单独用一个名字表示。
DEFAULT_PAGE = "首页"
DETAIL_PAGE = "详情"

# ---------------------------------------------------------------- 页面状态
# 所有页面跳转都依赖这几个 session_state 值，必须在页面渲染前先初始化。
# 注意：不要用 URL 参数或局部变量来做页面跳转，否则 st.rerun() 之后状态会丢失。
if "page" not in st.session_state:
    st.session_state["page"] = DEFAULT_PAGE

# 侧边栏单选按钮的选中值，和 page 分开保存。
# 这样详情页可以把 page 设成“详情”，同时侧边栏仍然停留在“首页”。
if "nav" not in st.session_state:
    st.session_state["nav"] = DEFAULT_PAGE

# 当前正在查看的物品 id；为 None 表示没有打开详情页。
if "detail_id" not in st.session_state:
    st.session_state["detail_id"] = None


# ---------------------------------------------------------------- 数据读取
def load_items():
    """读取全部记录，并确保数据表已经存在。"""
    db.init_db()
    return db.get_items()


def build_location_options(items):
    """把数据库中的地点去重、排序，并在最前面加上“全部”。"""
    locations = {item["location"] for item in items if item["location"]}
    return [ALL_LOCATIONS, *sorted(locations)]


def save_uploaded_image(uploaded_file):
    """把用户上传的图片保存到 uploads/ 文件夹，并返回保存后的文件名。

    uploaded_file 是 st.file_uploader 返回的对象。
    如果用户没有上传图片（值为 None），就返回空字符串。
    """
    if uploaded_file is None:
        return ""

    # 文件夹不存在就自动创建；已经存在也不会报错。
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # 从原文件名里取出后缀，例如 "cat.JPG" 会得到 ".jpg"。
    extension = os.path.splitext(uploaded_file.name)[1].lower()

    # 文件名使用当前时间戳（精确到微秒），这样每次上传都不会重名。
    filename = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + extension
    file_path = os.path.join(UPLOAD_DIR, filename)

    # getbuffer() 可以拿到上传文件的二进制内容，用 "wb" 模式写入。
    with open(file_path, "wb") as file:
        file.write(uploaded_file.getbuffer())

    # 返回文件名，发布时把它一起存进数据库，首页就能找到这张图片。
    return filename


# ---------------------------------------------------------------- 组件
# 全局自定义样式：状态进度条、悬赏金额高亮、图片全屏预览。
# 高亮步骤用绿色，尚未到达的步骤用灰色；配合 st.columns 使用。
CUSTOM_CSS = """
<style>
.lf-step {
    box-sizing: border-box;
    min-height: 48px;
    padding: 10px 6px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    font-size: 0.86rem;
    font-weight: 600;
    line-height: 1.25;
}
.lf-step--active {
    background: #e8f5e9;
    border: 1px solid #8fd19e;
    color: #1b5e20;
    box-shadow: 0 1px 3px rgba(27, 94, 32, 0.10);
}
.lf-step--pending {
    background: #f3f4f6;
    border: 1px solid #e5e7eb;
    color: #9ca3af;
}
.lf-step-arrow {
    color: #c4c8ce;
    font-size: 1.05rem;
    line-height: 48px;
    text-align: center;
}
.lf-progress-caption {
    margin-top: 0.55rem;
    color: #6b7280;
    font-size: 0.82rem;
    text-align: center;
}
/* 只给“有悬赏”的详情页指标数值上红色，类型、地点等不受影响。 */
.st-key-detail_bounty_paid [data-testid="stMetricValue"],
.st-key-detail_bounty_paid [data-testid="stMetricValue"] * {
    color: #d32f2f !important;
}
/* 首页缩略图：按最大高度封顶，竖屏照片不会把整张卡片撑得特别高。 */
[class*="st-key-card_image_"] [data-testid="stImageContainer"] {
    display: flex;
    align-items: center;
    justify-content: center;
}
[class*="st-key-card_image_"] [data-testid="stImage"] img {
    width: auto !important;
    height: auto !important;
    max-width: 100% !important;
    max-height: 180px !important;
    object-fit: contain !important;
    border-radius: 8px;
}
/* 详情页预览图比缩略图大，但同样限制高度，避免竖图无限拉长页面。 */
[class*="st-key-detail_image"] [data-testid="stImageContainer"] {
    display: flex;
    align-items: center;
    justify-content: center;
}
[class*="st-key-detail_image"] [data-testid="stImage"] img {
    width: auto !important;
    height: auto !important;
    max-width: 100% !important;
    max-height: 520px !important;
    object-fit: contain !important;
    border-radius: 10px;
}
/* Streamlit 的图片全屏层会沿用缩略图的固定宽度，导致大图不放大。
   注意：stFullScreenFrame 在普通状态下也存在于 DOM 中，不能直接选它，
   否则缩略图会被这条规则撑大。展开时内部会出现带 height 属性的容器，
   用这个特征只命中真正的全屏状态，再按视口重新计算图片尺寸。 */
[data-testid="stFullScreenFrame"] div[height] [data-testid="stImage"] img {
    width: auto !important;
    height: auto !important;
    max-width: 92vw !important;
    max-height: 86vh !important;
    object-fit: contain !important;
}
</style>
"""

# 样式必须在首页和详情页都生效，因此放在脚本入口统一注入一次。
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def render_status_badge(status):
    """渲染状态标签，未知状态按灰色显示。"""
    label, color = STATUS_META.get(status, (status, "gray"))
    st.badge(label, color=color)


def show_flash_message():
    """显示一次性的提示信息（例如“发布成功！”）。

    提示信息存在 st.session_state 里，显示一次后就删掉，
    这样页面刷新后不会一直重复出现。
    """
    message = st.session_state.get("flash_message")
    if message:
        st.success(message)
        del st.session_state["flash_message"]


def render_item_card(item):
    """把一条记录渲染成一张卡片。"""
    with st.container(border=True):
        title_col, badge_col = st.columns([4, 1], vertical_alignment="center")

        with title_col:
            st.markdown(f"**{item['title']}**")

        with badge_col:
            render_status_badge(item["status"])

        # 地点与悬赏金额放在同一行；悬赏金额用红色高亮，0 元时不显示悬赏。
        # 这里用 HTML 是为了精确控制颜色；地点来自数据库，先做转义防止注入。
        meta_parts = [f"地点：{html.escape(str(item['location']))}"]
        bounty = int(item.get("bounty") or 0)
        if bounty > 0:
            meta_parts.append(
                f'<span style="color:#d32f2f;font-weight:700;">'
                f"悬赏 ¥{bounty}"
                "</span>"
            )
        st.markdown(
            '<div style="font-size:0.875rem;color:#6b7280;">'
            + "　·　".join(meta_parts)
            + "</div>",
            unsafe_allow_html=True,
        )

        description = (item.get("description") or "").strip()
        if description:
            if len(description) > 120:
                description = description[:120] + "…"
            st.caption(description)

        # 如果这条记录保存过图片，就在卡片里显示缩略图。
        image_name = item.get("image_path") or ""
        if image_name:
            image_path = os.path.join(UPLOAD_DIR, image_name)
            # 先检查文件是否还在，避免图片被手动删除后页面报错。
            if os.path.exists(image_path):
                # 关键点：图片本身使用 width="stretch"，外层容器再限制为 320px。
                # 如果直接给 st.image 传固定像素宽度，Streamlit 的放大预览也会固定
                # 用这个像素宽度，导致点开大图后仍然只有缩略图大小。
                with st.container(
                    key=f"card_image_{item['id']}",
                    width=320,
                    horizontal_alignment="center",
                ):
                    st.image(
                        image_path,
                        width="stretch",
                        alt=f"{item['title']} 的图片",
                    )

        # 每张卡片底部都有一个详情入口。
        # key 里带上 id，保证不同卡片的按钮不会互相冲突。
        if st.button(
            "查看详情",
            key=f"view_detail_{item['id']}",
            use_container_width=True,
        ):
            # 先记住要看哪一条记录，再切换“真正的页面”。
            # 这里不直接改 nav，因为侧边栏单选按钮可能已经渲染过了；
            # page 独立于 nav，所以 st.rerun() 后可以稳定地显示详情页。
            st.session_state["detail_id"] = item["id"]
            st.session_state["page"] = DETAIL_PAGE
            st.rerun()


def render_item_list(item_type, location_options):
    """渲染一个 tab 内的搜索、筛选和列表。"""
    search_key = f"search_{item_type}"
    location_key = f"location_{item_type}"

    keyword = st.text_input(
        "搜索",
        placeholder="搜索标题、地点或描述",
        key=search_key,
    )
    selected_location = st.selectbox(
        "地点",
        options=location_options,
        key=location_key,
    )

    items = db.get_items(
        type_filter=item_type,
        keyword=keyword.strip() or None,
    )

    # 已完成的启事不再出现在首页列表里，只保留还在进行中/处理中的记录。
    items = [item for item in items if item.get("status") != "done"]

    if selected_location != ALL_LOCATIONS:
        items = [item for item in items if item["location"] == selected_location]

    st.caption(f"共 {len(items)} 条")
    st.write("")

    if not items:
        st.info("暂无符合条件的记录。")
        return

    for item in items:
        render_item_card(item)


# ---------------------------------------------------------------- 页面
def render_home():
    st.title("校园失物招领")
    st.caption("丢了东西，或者捡到了东西，都可以在这里找找看。")

    # 如果刚发布成功跳到首页，就在标题下面显示一次提示。
    show_flash_message()

    # 地点筛选也只从首页可见的记录里生成，避免下拉框出现只有已完成记录的地点。
    all_items = [
        item for item in load_items() if item.get("status") != "done"
    ]
    location_options = build_location_options(all_items)

    lost_tab, found_tab = st.tabs(
        [TYPE_LABELS["lost"], TYPE_LABELS["found"]]
    )

    with lost_tab:
        render_item_list("lost", location_options)

    with found_tab:
        render_item_list("found", location_options)


def get_progress_info(item):
    """返回（步骤名称列表，已高亮的步骤数量）。

    状态条分两套流程：
    - 有悬赏：4 步，悬赏金额由平台托管，确认后打款。
    - 无悬赏：3 步，线上匹配后线下交接。

    status 到高亮步骤数的映射：
    - open：只高亮第 1 步；
    - claimed：高亮前 2 步；
    - done：全部高亮。
    """
    bounty = int(item.get("bounty") or 0)
    if bounty > 0:
        steps = ["金额托管", "已提供线索", "失主确认", "打款完成"]
    else:
        steps = ["信息匹配", "线下交接", "标记完成"]

    status = item.get("status", "open")
    active_count = {
        "open": 1,
        "claimed": 2,
        "done": len(steps),
    }.get(status, 1)

    return steps, active_count


def render_progress_bar(item):
    """在详情页居中渲染状态进度条。"""
    steps, active_count = get_progress_info(item)
    bounty = int(item.get("bounty") or 0)
    status = item.get("status", "open")
    status_label = STATUS_META.get(status, (status, "gray"))[0]

    st.markdown("#### 处理进度")
    if bounty > 0:
        st.caption("有悬赏：金额先由平台托管，确认找回后扣除 8% 服务费并打款。")
    else:
        st.caption("无悬赏：线上确认信息，线下完成交接。")

    # 用 2n-1 列来排布：奇数位置放步骤格子，偶数位置放箭头。
    # 例如 4 个步骤会得到：[步骤1][→][步骤2][→][步骤3][→][步骤4]
    column_spec = []
    for index in range(len(steps)):
        column_spec.append(1)
        if index < len(steps) - 1:
            column_spec.append(0.16)

    columns = st.columns(column_spec, gap="small")

    for index, step_name in enumerate(steps):
        # 前 active_count 步为绿色高亮，后面的步骤统一灰色。
        is_active = index < active_count
        step_class = "lf-step--active" if is_active else "lf-step--pending"
        prefix = "✓" if is_active else f"{index + 1}."

        with columns[index * 2]:
            st.markdown(
                f'<div class="lf-step {step_class}">'
                f"{prefix} {step_name}"
                "</div>",
                unsafe_allow_html=True,
            )

        # 步骤之间画一个灰色箭头。
        if index < len(steps) - 1:
            with columns[index * 2 + 1]:
                st.markdown(
                    '<div class="lf-step-arrow">→</div>',
                    unsafe_allow_html=True,
                )

    st.markdown(
        '<div class="lf-progress-caption">'
        f"当前状态：{status_label}　·　已完成 {active_count}/{len(steps)} 步"
        "</div>",
        unsafe_allow_html=True,
    )


def show_detail_flash(item_id):
    """显示一次性的详情页操作提示。

    按钮里执行完数据库更新后会马上 st.rerun()，所以 st.success 不能直接写在
    按钮分支里（那一轮页面会被丢弃）。先把提示存进 session_state，刷新后再显示。
    """
    flash = st.session_state.pop("detail_flash", None)
    if flash and flash.get("item_id") == item_id:
        st.success(flash["message"])


def render_detail():
    """详情页：读取 detail_id，展示完整信息、状态条和状态流转按钮。"""
    # 返回按钮放在页面最顶部。点击后同时清理 detail_id 和 page，
    # 这样回到首页时不会残留上一次打开的详情。
    if st.button("← 返回首页", key="detail_back"):
        st.session_state.pop("detail_id", None)
        st.session_state.pop("detail_flash", None)
        st.session_state["page"] = DEFAULT_PAGE
        st.rerun()

    detail_id = st.session_state.get("detail_id")
    if detail_id is None:
        st.warning("还没有选择要查看的物品，请先返回首页。")
        return

    # 详情页也可能在应用刚启动时被直接打开，所以这里确保数据表存在。
    db.init_db()
    item = db.get_item(detail_id)
    if item is None:
        st.error("没有找到这条记录，它可能已经被删除。")
        return

    show_detail_flash(item["id"])

    # ------------------------------------------------------------ 完整信息
    title_col, badge_col = st.columns([4, 1], vertical_alignment="center")
    with title_col:
        st.title(item["title"])
    with badge_col:
        render_status_badge(item["status"])

    created_at = item.get("created_at") or "未知时间"
    st.caption(
        f"{TYPE_LABELS.get(item['type'], item['type'])}　·　发布于 {created_at}"
    )

    # ------------------------------------------------------------ 联系方式
    # 联系方式是失主和拾得者建立联系的关键信息，放在标题下方最醒目的位置。
    # 用 .get() 读取，兼容升级前就存在、contact 为空字符串的旧记录。
    contact = (item.get("contact") or "").strip()
    st.info(f"📞 联系方式：{contact if contact else '发布者未填写'}")
    # 温馨提醒：提醒双方线下当面交接，避免线上转账或泄露过多个人信息。
    st.caption("🤝 温馨提醒：请在校内安全地点当面交接，核验物品后再付款。")

    bounty = int(item.get("bounty") or 0)
    type_col, location_col, bounty_col = st.columns(3)
    with type_col:
        st.metric("类型", TYPE_LABELS.get(item["type"], item["type"]))
    with location_col:
        st.metric("地点", item["location"])
    with bounty_col:
        # 悬赏为 0 时显示“无悬赏”，避免用户误以为金额缺失。
        # 有悬赏时给容器一个专用 key，配合 CSS 只把这个指标的数字变红。
        bounty_metric_key = (
            "detail_bounty_paid" if bounty > 0 else "detail_bounty_none"
        )
        with st.container(key=bounty_metric_key):
            st.metric(
                "悬赏金额",
                f"¥{bounty}" if bounty > 0 else "无悬赏",
            )

    st.markdown("**描述**")
    description = (item.get("description") or "").strip()
    st.write(description if description else "暂无描述。")

    # 如果发布时上传过图片，详情页展示原图。
    image_name = item.get("image_path") or ""
    if image_name:
        image_path = os.path.join(UPLOAD_DIR, image_name)
        if os.path.exists(image_path):
            # 详情页展示得更大，但同样使用 stretch 而不是固定像素宽度，
            # 这样点击图片进入全屏预览时，图片才会按屏幕大小真正放大。
            with st.container(
                key="detail_image",
                width=520,
                horizontal_alignment="center",
            ):
                st.image(
                    image_path,
                    width="stretch",
                    alt=f"{item['title']} 的图片",
                )

    st.divider()

    # ------------------------------------------------------------ 状态进度条
    render_progress_bar(item)

    st.divider()

    # ------------------------------------------------------------ 状态流转
    st.markdown("#### 操作")
    status = item.get("status")
    item_id = item["id"]

    if status == "open":
        # 寻物信息由拾得者提供线索；招领信息由失主申请认领。
        button_label = (
            "我找到了 / 提供线索"
            if item["type"] == "lost"
            else "这是我的，申请认领"
        )
        if st.button(
            button_label,
            key=f"advance_open_{item_id}",
            type="primary",
            use_container_width=True,
        ):
            # open -> claimed
            if db.update_status(item_id, "claimed"):
                st.session_state["detail_flash"] = {
                    "item_id": item_id,
                    "message": (
                        "线索已提交，等待失主确认。"
                        if item["type"] == "lost"
                        else "认领申请已提交，等待拾得者确认。"
                    ),
                }
                st.rerun()
            else:
                st.error("状态更新失败，这条记录可能已经被删除。")

    elif status == "claimed":
        if bounty > 0:
            # 有悬赏：claimed -> done，演示平台放款。
            st.info(f"悬赏 ¥{bounty} 正在平台托管中（演示）。")
            if st.button(
                "确认找回，放款（演示）",
                key=f"advance_paid_{item_id}",
                type="primary",
                use_container_width=True,
            ):
                if db.update_status(item_id, "done"):
                    # rerun 之后由 show_detail_flash() 显示这条成功提示。
                    st.session_state["detail_flash"] = {
                        "item_id": item_id,
                        "message": "已从托管账户扣除 8% 服务费，打款给拾得者！",
                    }
                    st.rerun()
                else:
                    st.error("状态更新失败，这条记录可能已经被删除。")
        else:
            # 无悬赏：claimed -> done，确认线下交接完成。
            if st.button(
                "确认线下交接完成",
                key=f"advance_offline_{item_id}",
                type="primary",
                use_container_width=True,
            ):
                if db.update_status(item_id, "done"):
                    st.session_state["detail_flash"] = {
                        "item_id": item_id,
                        "message": "线下交接已完成，该物品已标记为完成。",
                    }
                    st.rerun()
                else:
                    st.error("状态更新失败，这条记录可能已经被删除。")

    elif status == "done":
        # 已完成时只展示提示，不再提供任何操作按钮。
        st.success("该物品已成功找回/交接。")

    else:
        # 正常情况下不会走到这里；保留兜底，避免旧数据导致页面空白。
        st.warning(f"未知状态：{status}")


def render_publish():
    """发布页面：填写表单 → 保存图片 → 写入数据库 → 回到首页。"""
    st.title("发布")
    st.caption("在这里发布寻物或招领信息。")

    # 用 st.form 把输入框包起来：填写过程中页面不会反复刷新，
    # 只有点击“确认发布”按钮时，才会把这一组数据一起提交上来。
    with st.form("publish_form", clear_on_submit=True):
        # 类型：用户看到的是“寻物 (lost)”这种写法，提交后再转换成 "lost"。
        type_label = st.radio(
            "类型",
            options=list(TYPE_CHOICES.keys()),
            horizontal=True,
        )

        title = st.text_input(
            "物品名称",
            placeholder="例如：黑色雨伞",
        )

        location = st.selectbox(
            "地点",
            options=PUBLISH_LOCATIONS,
        )

        description = st.text_area(
            "描述",
            placeholder="例如：颜色、品牌、丢失的大概时间等",
        )

        # 联系方式是必填项：失主和拾得者要靠它互相联系。
        # 手机号或微信号都可以，这里不做格式校验，只要求非空。
        contact = st.text_input(
            "联系方式 (手机号/微信号)",
            placeholder="例如：微信 test123 / 手机号 138xxxxxxxx",
        )

        # min_value=0、value=0、step=5，单位在标签里写成“元”。
        bounty = st.number_input(
            "悬赏金额（元）",
            min_value=0,
            value=0,
            step=5,
            format="%d",
        )

        uploaded_file = st.file_uploader(
            "图片（可选）",
            type=["jpg", "jpeg", "png"],
            help="支持 jpg / png 格式，只能上传一张。",
        )

        # 表单的提交按钮，type="primary" 会让它变成醒目的主按钮。
        submitted = st.form_submit_button("确认发布", type="primary")

    # 没有点击提交按钮时，只显示表单，下面的代码不执行。
    if not submitted:
        return

    # 简单检查一下必填项：物品名称和联系方式都不能为空。
    title = title.strip()
    if not title:
        st.error("请填写物品名称。")
        return

    # 联系方式同样是必填项，否则详情页无法提供有效的联系途径。
    contact = contact.strip()
    if not contact:
        st.error("请填写联系方式（手机号/微信号）。")
        return

    # 把界面上的“寻物 (lost)”转换成数据库需要的 "lost" 或 "found"。
    item_type = TYPE_CHOICES[type_label]

    # 如果上传了图片，就先保存到 uploads/ 文件夹，并拿到文件名。
    image_name = save_uploaded_image(uploaded_file)

    # 把数据写入数据库。
    # number_input 返回的本来就是整数，这里再 int() 一次只是为了更保险。
    db.add_item(
        item_type=item_type,
        title=title,
        location=location,
        description=description.strip(),
        bounty=int(bounty),
        image_path=image_name,
        contact=contact,
    )

    # 整理成功提示；有悬赏金额时，再追加一句演示用的说明。
    message = "发布成功！"
    if bounty > 0:
        message += f"悬赏 ¥{int(bounty)} 已进入平台托管状态（演示）"

    st.success(message)

    # 马上要调用 st.rerun()，当前这一轮的页面内容会被丢弃，
    # 所以先把提示、目标页面和“侧边栏要切回首页”记到 session_state 里，
    # 下一轮脚本开头会先应用这些状态。
    st.session_state["flash_message"] = message
    st.session_state["page"] = DEFAULT_PAGE
    st.session_state["goto_page"] = DEFAULT_PAGE

    # 刷新页面，自动跳回首页，方便用户马上看到刚发布的信息。
    st.rerun()


def render_profile():
    """“我的”页面：志愿记录、信用分和最近发布。"""
    st.title("我的")
    st.caption("查看志愿服务记录、信用分和我发布的内容。")

    # 志愿记录的数字不再写死，每次进入页面都从数据库动态统计：
    # - done_total：status == 'done' 的全部物品总数（累计寻回）。
    # - free_total：status == 'done' 且 bounty == 0 的数量（免费志愿服务）。
    # 目前没有登录系统，统计的是本机数据库里的全部记录（单机演示）。
    db.init_db()
    stats = db.get_volunteer_stats()
    total_done = stats["done_total"]
    free_done = stats["free_total"]

    # 志愿记录单独一张卡片，内部按“第一行 / 第二行”排布。
    with st.container(border=True):
        st.markdown("#### 🧾 志愿服务记录")

        # 第一行：累计寻回物品总次数（status == 'done'）。
        # 用 st.columns 把“数字”和“统计口径说明”分成两列，避免说明文字挤在数字下面。
        total_row = st.columns([1, 1.7], vertical_alignment="center")
        with total_row[0]:
            st.metric(
                "累计寻回物品",
                f"{total_done} 次",
                help="统计数据库中状态为「已完成」(done) 的全部启事数量。",
            )
        with total_row[1]:
            st.caption("包含有悬赏和无悬赏的全部已完成记录。")

        # 第二行：免费志愿服务次数（status == 'done' 且 bounty == 0）。
        # 这个数字专门用于对接综测加分，所以用小字注明用途。
        free_row = st.columns([1, 1.7], vertical_alignment="center")
        with free_row[0]:
            st.metric(
                "免费志愿服务",
                f"{free_done} 次",
                help="统计状态为「已完成」且悬赏金额为 0 的启事数量。",
            )
        with free_row[1]:
            st.caption("（此数据可用于导出综测证明）")

        # 下方保留导出按钮；点击后在本页给出演示用的导出提示。
        export_clicked = st.button(
            "导出志愿记录证明",
            key="export_volunteer_record",
            width="stretch",
        )

    # 导出提示放在卡片下方通栏显示，长句子不会被狭窄的卡片挤成很多行。
    if export_clicked:
        st.info(
            f"已生成《校园寻物志愿服务记录》：累计寻回 {total_done} 次，"
            f"其中免费志愿服务 {free_done} 次。{VOLUNTEER_EXPORT_NOTICE}"
        )

    # 信用分模块放在志愿记录下方，继续保持整行宽度，信息更清楚。
    with st.container(border=True):
        st.markdown("#### ⭐ 信用分")
        st.metric("当前信用分", CREDIT_SCORE)
        st.badge("信用良好", color="green")
        st.caption(
            f"信用分 ≥ {CREDIT_THRESHOLD} 可正常发布悬赏与认领；"
            "低于阈值将限制权限。"
        )

    st.divider()

    # ------------------------------------------------------------ 我的发布
    st.subheader("我的发布")

    # 每次进入页面都重新读取数据库，发布或状态变化后能立刻反映出来。
    items = load_items()
    recent_items = items[:PROFILE_RECENT_LIMIT]

    if not recent_items:
        st.caption("共 0 条记录。")
        st.info("还没有发布记录，去“发布”页面创建第一条吧。")
        return

    st.caption(
        f"共 {len(items)} 条记录，按发布时间倒序展示最近 "
        f"{len(recent_items)} 条。"
    )

    # 表格里只放必要字段，并把类型、状态换成中文名称。
    rows = []
    for item in recent_items:
        status_label = STATUS_META.get(item["status"], (item["status"], "gray"))[0]
        rows.append(
            {
                "标题": item["title"],
                "类型": TYPE_LABELS.get(item["type"], item["type"]),
                "状态": status_label,
                "发布时间": item.get("created_at") or "—",
            }
        )

    st.dataframe(
        rows,
        width="stretch",
        hide_index=True,
        column_order=["标题", "类型", "状态", "发布时间"],
        column_config={
            "标题": st.column_config.TextColumn("标题", width="large"),
            "类型": st.column_config.TextColumn("类型", width="small"),
            "状态": st.column_config.TextColumn("状态", width="small"),
            "发布时间": st.column_config.TextColumn("发布时间", width="medium"),
        },
    )


# ---------------------------------------------------------------- 侧边栏导航
PAGES = {
    "首页": render_home,
    "发布": render_publish,
    "我的": render_profile,
}


def handle_nav_change():
    """用户点击侧边栏时，以单选按钮的新值为准切换页面。

    这个回调会在下一次脚本运行“创建 radio 之前”执行，
    所以可以安全地修改 page，也可以顺便清空详情页状态。
    """
    st.session_state["page"] = st.session_state["nav"]
    st.session_state.pop("detail_id", None)
    st.session_state.pop("detail_flash", None)


# 发布成功后需要自动跳回首页。
# 但导航控件（下面 key="nav" 的单选框）一旦创建，就不能再改它的值，
# 所以要在创建控件之前，先把“想跳转到的页面”写进 session_state。
if "goto_page" in st.session_state:
    target_page = st.session_state.pop("goto_page")
    # 只接受侧边栏里真实存在的常规页面，防止脏数据把页面路由带偏。
    if target_page in PAGES:
        st.session_state["nav"] = target_page
        st.session_state["page"] = target_page

with st.sidebar:
    st.title("校园失物招领")
    st.caption("失物招领信息平台")
    st.divider()
    # 注意：这里不再把 radio 的返回值直接当作页面。
    # page 才是路由状态；详情页可以在 radio 仍显示“首页”时独立打开。
    st.radio(
        "导航",
        options=list(PAGES),
        key="nav",
        label_visibility="collapsed",
        on_change=handle_nav_change,
    )

# 根据 page 渲染页面。“详情”不在 PAGES 里，需要单独处理。
current_page = st.session_state.get("page", DEFAULT_PAGE)
if current_page == DETAIL_PAGE:
    render_detail()
else:
    # 如果 session_state 里出现未知页面，兜底回首页，避免白屏。
    PAGES.get(current_page, render_home)()