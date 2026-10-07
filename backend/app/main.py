from fastapi import FastAPI
from .api.sales import router as sales_router
from .api.v2 import router as v2_router

app = FastAPI(title="PeCal Sales Assistant", version="0.2.0")
app.include_router(sales_router)
app.include_router(v2_router)
