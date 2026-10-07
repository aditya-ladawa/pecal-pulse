from fastapi import FastAPI
from .api.sales import router

app = FastAPI(title="PeCal Sales Assistant — Mock API", version="0.1.0")
app.include_router(router)
