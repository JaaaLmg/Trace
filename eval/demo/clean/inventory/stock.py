# Demo inventory module for seeded bug benchmark tasks.
import math


def has_stock(available, requested):
    return available >= requested


def reorder_quantity(current, threshold, target):
    if current <= threshold:
        return target - current
    return 0


def clamp_quantity(quantity):
    if quantity < 0:
        return 0
    return quantity


def pack_count(items, pack_size):
    return math.ceil(items / pack_size)
