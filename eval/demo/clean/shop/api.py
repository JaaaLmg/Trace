# 被测对象：一个最小 FastAPI 路由，覆盖「错状态码」这类 bug。
from fastapi import FastAPI, HTTPException

from shop.pricing import apply_discount

app = FastAPI()

_PRICES = {"book": 30.0, "pen": 2.5}


@app.get("/price/{item}")
def get_price(item: str, member: bool = False):
    if item not in _PRICES:
        raise HTTPException(status_code=404, detail="item not found")
    return {"item": item, "total": apply_discount(_PRICES[item], member)}
