# Demo account policy module for seeded bug benchmark tasks.


def can_withdraw(balance, amount):
    return balance >= amount


def overdraft_fee(days_late):
    if days_late <= 0:
        return 0
    if days_late <= 3:
        return 10
    return 25


def clamp_interest_rate(rate):
    if rate < 0:
        return 0.0
    if rate > 0.35:
        return 0.35
    return rate


def risk_tier(score):
    if score >= 700:
        return "low"
    if score >= 600:
        return "medium"
    return "high"
