import uuid


def new_id() -> str:
    # V1 主键用 uuid4 字符串；B 接 DB 时可改成数据库默认值，调用方不感知
    return str(uuid.uuid4())
