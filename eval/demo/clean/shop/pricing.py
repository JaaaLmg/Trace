# 被测对象：一个最小购物计价模块。纯函数，断言语义清晰，便于 seeded bug 评测。
# 注意：种子 bug 都设计成「返回错值」而非「该抛却不抛」——捕获率只认 assertion failure。


def apply_discount(total, is_member):
    # 会员且满 100 元打 9 折
    if is_member and total >= 100:
        return round(total * 0.9, 2)
    return round(total, 2)


def shipping_fee(weight_kg):
    # 5kg 及以内统一 10 元，超出 20 元
    if weight_kg <= 5:
        return 10
    return 20


def clamp_discount_rate(rate):
    # 折扣率必须落在 [0, 1]
    if rate < 0:
        return 0.0
    if rate > 1:
        return 1.0
    return rate


def is_free_shipping(total):
    # 满 200 元包邮
    return total >= 200


def loyalty_points(years):
    # 满 3 年送 100 分，否则 10 分
    if years >= 3:
        return 100
    return 10
