"""雾歇香薰 · AI 客服后端入口。

启动时初始化一次混合检索器（复用同一实例），SSE 接口见 chat.py。
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from chat import init_retriever, router as chat_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时加载一次 FAISS 索引与 chunks；整个进程复用同一 retriever 实例。
    app.state.retriever = init_retriever()
    yield


app = FastAPI(title="雾歇香薰 AI 客服后端", lifespan=lifespan)

# 允许的本地开发来源：
# - http://localhost:8000：本地起的前端开发服务器
# - "null"：通过 file:// 协议直接打开前端页面时，浏览器发送的 Origin 为 "null"
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "null"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)


@app.get("/")
async def root():
    return {"message": "雾歇香薰 AI 客服后端运行中"}


@app.get("/health")
async def health():
    return {"status": "ok"}
