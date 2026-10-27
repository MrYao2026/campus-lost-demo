# -*- coding: utf-8 -*-
"""生成校园失物招领的测试数据。

运行方式（在 D:\\vsc\\demo 目录下）：
    .\\.venv\\Scripts\\python.exe seed.py

每次运行都会：
1. 先调用 db.reset_db() 删除并重建 items 表，
   这样新增的 contact 字段一定能生效（SQLite 不好直接改已有表结构）；
2. 再重新插入 6 条测试数据，每条数据随机生成一个假联系方式。

注意：reset_db() 会清空全部旧数据。
运行前建议先停止正在运行的 Streamlit 服务，避免数据库被占用。
"""

import random

# reset_db()：重置表结构（DROP TABLE + CREATE TABLE）。
# add_item()：插入单条记录。
# 这里不需要 init_db()，因为 reset_db() 已经负责建表了。
from db import add_item, reset_db


# 测试数据：每条记录包含
# (类型, 物品名称, 地点, 描述, 悬赏金额)
# 联系方式在插入时随机生成，不写在这里。
TEST_ITEMS = [
    # 2 条寻物，有悬赏
    ("lost", "黑色无线耳机", "图书馆", "在图书馆三楼自习区丢失，充电盒是白色的。", 30),
    ("lost", "宿舍钥匙", "操场", "钥匙串上有蓝色挂件，一共三把钥匙。", 50),

    # 2 条寻物，无悬赏
    ("lost", "校园卡", "第二食堂", "午饭时落在餐桌上，请捡到的同学联系我。", 0),
    ("lost", "蓝色雨伞", "教学楼A", "落在教学楼A 201 教室，伞柄上有一道划痕。", 0),

    # 2 条招领，无悬赏
    ("found", "保温杯", "图书馆", "在图书馆一楼大厅捡到，银色保温杯。", 0),
    ("found", "黑色书包", "教学楼A", "在教学楼A 305 教室捡到，里面有几本教材。", 0),
]


def random_contact():
    """随机生成一条假的联系方式（微信号或手机号）。

    仅用于演示：号码全部是虚构的，请勿用于真实联系。
    """
    # 各 50% 概率生成微信号或手机号。
    if random.random() < 0.5:
        # 微信号：test + 3 位随机数字，例如 "微信: test428"
        return f"微信: test{random.randint(100, 999)}"

    # 手机号：138 开头 + 8 位随机数字（演示用的假号码）
    tail = "".join(random.choice("0123456789") for _ in range(8))
    return f"手机号: 138{tail}"


def generate_contacts(count):
    """生成 count 个互不重复的假联系方式。

    用 set 去重，避免 6 条测试数据里出现相同的联系方式，
    演示时看起来更像真实数据。
    """
    contacts = set()
    while len(contacts) < count:
        contacts.add(random_contact())
    # set 转 list 后顺序是随机的，这里不需要固定顺序。
    return list(contacts)


def main():
    """重置数据库、生成联系方式、插入测试数据。"""
    # 第一步：重置数据库。
    # 直接 DROP TABLE 再 CREATE TABLE，保证 items 表按最新结构创建，
    # 新增的 contact 字段才会生效（旧表无法直接加列时用这个办法）。
    reset_db()

    # 第二步：为每条测试数据准备一个随机联系方式。
    contacts = generate_contacts(len(TEST_ITEMS))

    # 第三步：逐条插入，并打印插入结果。
    for (item_type, title, location, description, bounty), contact in zip(
        TEST_ITEMS, contacts
    ):
        add_item(
            item_type=item_type,
            title=title,
            location=location,
            description=description,
            bounty=bounty,
            contact=contact,
        )
        print(f"已插入：{title}（联系方式：{contact}）")

    print(f"完成，共插入 {len(TEST_ITEMS)} 条测试数据。")


if __name__ == "__main__":
    main()