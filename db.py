"""校园失物招领的数据库操作。

只使用 Python 标准库 sqlite3，不依赖 ORM 或 SQLAlchemy。
数据库文件 campus_lost.db 会自动创建在 db.py 所在的目录中。

本模块提供：
- init_db()：建表，并自动为旧数据库补齐新增的字段（不丢数据）。
- reset_db()：删除并重建 items 表（会清空全部数据，用于升级表结构）。
- add_item() / get_item() / get_items() / update_status()：基本的增删改查。
- count_done_items() / count_free_done_items() / get_volunteer_stats()：
  为“我的”页面统计志愿记录（累计寻回、免费志愿服务）。
"""

import os
import sqlite3

# 数据库文件路径。
# 使用 db.py 所在目录，这样无论从哪个目录运行程序，都会使用同一个数据库文件。
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "campus_lost.db")

# 表中允许的类型和状态，方便在函数里做检查。
VALID_TYPES = ("lost", "found")
VALID_STATUSES = ("open", "claimed", "done")

# 建表语句：id 自增，type 和 status 只能取指定值。
# contact 保存发布者的联系方式（手机号或微信号），发布页会强制填写。
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK (type IN ('lost', 'found')),
    title TEXT NOT NULL,
    location TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    bounty INTEGER NOT NULL DEFAULT 0 CHECK (bounty >= 0),
    image_path TEXT NOT NULL DEFAULT '',
    contact TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'claimed', 'done')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

# 查询时要取出的列。
# 统一写成常量，避免 get_item 和 get_items 的字段列表不一致。
ITEM_COLUMNS = (
    "id, type, title, location, description, bounty, "
    "image_path, contact, status, created_at"
)


def init_db():
    """创建 items 表，并兼容旧版本的数据库。

    如果表已经存在，就什么都不做，不会清空已有数据。
    对于旧版本创建的表，缺少的字段（image_path、contact）会在这里用
    ALTER TABLE ADD COLUMN 补上，这样已有记录不会丢失。
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(CREATE_TABLE_SQL)

        # 检查现有表有哪些列，缺少的列就补上。
        columns = [row[1] for row in conn.execute("PRAGMA table_info(items)")]

        # 旧版本没有 image_path；第 8 步升级后新增了 contact。
        # SQLite 的 ALTER TABLE 只能往末尾追加列，这里正合适。
        migrations = {
            "image_path": (
                "ALTER TABLE items ADD COLUMN image_path TEXT NOT NULL DEFAULT ''"
            ),
            "contact": (
                "ALTER TABLE items ADD COLUMN contact TEXT NOT NULL DEFAULT ''"
            ),
        }
        for column, alter_sql in migrations.items():
            if column not in columns:
                conn.execute(alter_sql)

        conn.commit()
    finally:
        # 无论成功还是出错，最后都要关闭连接。
        conn.close()


def reset_db():
    """重置数据库：删除 items 表并重新创建（会清空全部数据）。

    为什么需要这个函数：
    SQLite 的 ALTER TABLE 只能追加列，不能修改已有列的类型或约束。
    当表结构需要调整（例如新增 contact 字段）时，旧表直接加列虽然可行，
    但如果要让表结构完全按 CREATE_TABLE_SQL 重建，最干净的办法就是
    DROP TABLE + CREATE TABLE。

    使用场景：seed.py 生成演示数据前调用，保证新字段一定生效。
    注意：这是破坏性操作，正式环境不要随便调用。
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        # IF EXISTS：第一次运行时表可能还不存在，加了这个关键字就不会报错。
        conn.execute("DROP TABLE IF EXISTS items")

        # 自增计数器保存在 sqlite_sequence 表里。
        # 如果数据库从来没有创建过自增表，这张表本身就不存在，忽略即可。
        try:
            conn.execute("DELETE FROM sqlite_sequence WHERE name = 'items'")
        except sqlite3.OperationalError:
            pass

        # 用最新的建表语句重建，新字段（contact）随之生效。
        conn.execute(CREATE_TABLE_SQL)
        conn.commit()
    finally:
        conn.close()


def add_item(
    item_type,
    title,
    location,
    description="",
    bounty=0,
    image_path="",
    contact="",
):
    """插入一条失物或招领信息，并返回新记录的 id。

    item_type：只能是 "lost"（丢失）或 "found"（捡到）。
    title：物品名称。
    location：丢失或捡到的地点。
    description：详细描述，可以不填。
    bounty：悬赏金额，必须是不小于 0 的整数，默认 0。
    image_path：图片文件名（保存在 uploads/ 文件夹里的名字），没有图片时为空字符串。
    contact：联系方式（手机号 / 微信号），发布页强制填写，这里默认为空字符串。
    """
    if item_type not in VALID_TYPES:
        raise ValueError("item_type 只能是 'lost' 或 'found'")
    if not isinstance(bounty, int) or bounty < 0:
        raise ValueError("bounty 必须是不小于 0 的整数")

    # 联系方式首尾的多余空格去掉，避免用户误输入空格导致页面显示空白。
    # 允许为空（兼容旧数据 / 脚本调用），是否必填由发布页（app.py）负责校验。
    contact = str(contact or "").strip()

    conn = sqlite3.connect(DB_PATH)
    try:
        # 使用 ? 占位符传参，可以避免 SQL 注入问题。
        cursor = conn.execute(
            """
            INSERT INTO items
                (type, title, location, description, bounty, image_path, contact)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (item_type, title, location, description, bounty, image_path, contact),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_items(type_filter=None, keyword=None):
    """按类型和关键词查询记录，返回由字典组成的列表。

    type_filter：为 None 时查询全部类型，否则按 "lost" 或 "found" 筛选。
    keyword：为 None 或空字符串时不搜索；否则在标题、地点、描述中模糊搜索。
    结果按创建时间从新到旧排列。
    """
    if type_filter is not None and type_filter not in VALID_TYPES:
        raise ValueError("type_filter 只能是 None、'lost' 或 'found'")

    # 先写固定的查询部分，再根据传入的条件拼接 WHERE 子句。
    sql = f"""
        SELECT {ITEM_COLUMNS}
        FROM items
    """
    conditions = []
    params = []

    if type_filter is not None:
        conditions.append("type = ?")
        params.append(type_filter)

    if keyword:
        # LIKE 配合 % 表示“包含这个关键词”。
        like_pattern = "%" + keyword + "%"
        conditions.append(
            "(title LIKE ? OR location LIKE ? OR description LIKE ?)"
        )
        params.extend([like_pattern, like_pattern, like_pattern])

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    sql += " ORDER BY created_at DESC, id DESC"

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # 让查询结果可以按列名读取。
    try:
        rows = conn.execute(sql, params).fetchall()
        # 把 sqlite3.Row 转成普通字典，页面或其他代码使用起来更方便。
        return [dict(row) for row in rows]
    finally:
        conn.close()


def update_status(item_id, new_status):
    """更新指定记录的状态。

    new_status 只能是 "open"、"claimed" 或 "done"。
    更新成功返回 True；如果这个 id 不存在，返回 False。
    """
    if new_status not in VALID_STATUSES:
        raise ValueError("new_status 只能是 'open'、'claimed' 或 'done'")

    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.execute(
            "UPDATE items SET status = ? WHERE id = ?",
            (new_status, item_id),
        )
        conn.commit()
        # rowcount 表示实际修改了几行；0 行说明没有找到对应记录。
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_item(item_id):
    """按 id 查询一条记录。

    找到时返回一个字典，找不到时返回 None。
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            f"""
            SELECT {ITEM_COLUMNS}
            FROM items
            WHERE id = ?
            """,
            (item_id,),
        ).fetchone()

        if row is None:
            return None
        return dict(row)
    finally:
        conn.close()


# ---------------------------------------------------------------- 志愿记录统计
# 目前没有账号体系（单机演示），所以这里统计的是数据库中所有满足条件的记录。
# 接入登录系统后，只需要给这两个 SQL 加上 "AND user_id = ?" 之类的条件即可。
def count_done_items():
    """统计累计寻回次数：status == 'done' 的全部物品总数。

    对应 SQL：
        SELECT COUNT(*) FROM items WHERE status = 'done'
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM items WHERE status = 'done'"
        ).fetchone()
        # COUNT 永远返回一行，row[0] 就是数量；兜底用 or 0 防止 None。
        return int(row[0] or 0)
    finally:
        conn.close()


def count_free_done_items():
    """统计免费志愿服务次数：status == 'done' 且 bounty == 0 的物品总数。

    免费（无悬赏）的已完成记录才计入志愿服务，用于综测加分。
    对应 SQL：
        SELECT COUNT(*) FROM items WHERE status = 'done' AND bounty = 0
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM items WHERE status = 'done' AND bounty = 0"
        ).fetchone()
        return int(row[0] or 0)
    finally:
        conn.close()


def get_volunteer_stats():
    """一次性返回“我的”页面需要的两个志愿记录数字。

    返回值是字典：
    - done_total：累计寻回物品总次数（status == 'done'）。
    - free_total：免费志愿服务次数（status == 'done' 且 bounty == 0）。

    用一条 SQL 同时算出两个数，比分别查两次少开一次数据库连接。
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS done_total,
                -- 免费志愿服务：已完成且没有悬赏（bounty = 0）
                COALESCE(SUM(CASE WHEN bounty = 0 THEN 1 ELSE 0 END), 0)
                    AS free_total
            FROM items
            WHERE status = 'done'
            """
        ).fetchone()
        return {
            "done_total": int(row[0] or 0),
            "free_total": int(row[1] or 0),
        }
    finally:
        conn.close()


if __name__ == "__main__":
    # 直接运行 python db.py 时，创建数据库和 items 表。
    # 加上 --reset 参数则重建表结构（会清空所有数据）：
    #     python db.py --reset
    import sys

    if "--reset" in sys.argv[1:]:
        reset_db()
        print("数据库已重置（items 表已删除并重建）：", DB_PATH)
    else:
        init_db()
        print("数据库初始化完成：", DB_PATH)