# uvicorn main:app --reload
import uvicorn
import asyncio
from rota_funcs import abuild_rota_data as build_rota
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from env.secret import db_login

from api.login import login_router
from api.get_rota import get_rota_router


app = FastAPI()
app.include_router(login_router)
app.include_router(get_rota_router)

origins = [
    "https://zithr.github.io",
] + [f"http://localhost:{i}" for i in range(1, 2 ** 16)]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if __name__ == "__main__":
    # asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # print(asyncio.run(build_rota()))
    uvicorn.run("__main__:app", host="0.0.0.0", port=8000, reload=True)
