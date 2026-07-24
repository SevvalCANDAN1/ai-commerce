from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import close_database_connection, connect_to_database


from app.models.product import Product
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.routers import auth, product


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_database(document_models=[User, Product, RefreshToken])
    yield
    await close_database_connection()


app = FastAPI(
    title="AI-Commerce API",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(product.router, prefix="/api/v1")

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "ai-commerce"}

