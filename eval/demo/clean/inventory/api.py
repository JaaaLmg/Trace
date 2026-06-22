from fastapi import FastAPI, HTTPException

from inventory.stock import has_stock

app = FastAPI()

_STOCK = {"pencil": 8, "notebook": 3}


@app.get("/sku/{sku}")
def get_sku(sku: str, requested: int = 1):
    if sku not in _STOCK:
        raise HTTPException(status_code=404, detail="sku not found")
    available = _STOCK[sku]
    return {"sku": sku, "available": available, "can_fulfill": has_stock(available, requested)}
