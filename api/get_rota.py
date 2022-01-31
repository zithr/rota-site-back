from typing import Optional
from fastapi import HTTPException, Cookie
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter
from pydantic import BaseModel
import aiohttp, asyncio
import pendulum
from loguru import logger
from rota_funcs import abuild_rota_data
from env.secret import test_url
import sys

get_rota_router = APIRouter()

async def test_is_logged_in(cookies) -> bool:  # TODO pull cookiejar from FE
    async with aiohttp.ClientSession(cookies=cookies) as session:
        res = await session.get(test_url, allow_redirects=False)
        status = res.status
        if status != 200:
            logger.info("Not logged in")
            raise HTTPException(status_code=401, detail="Invalid login")
        logger.info("Logged in")
        return True

@get_rota_router.get("/api/rota")
async def get_rota(day: int = pendulum.today().day, month: int = pendulum.today().month, year: int = pendulum.today().year, _o6_session: Optional[str] = Cookie(None), account_credentials: Optional[str] = Cookie(None)):
    cookies = {"_o6_session": _o6_session,"account_credentials": account_credentials}
    start_date = pendulum.date(year, month, day)
    try:
        rota = await abuild_rota_data(cookies=cookies, start_date=start_date)
    except aiohttp.TooManyRedirects:
        logger.info(f"redirect error: {sys.exc_info()[0]}")
        return
    if not rota:
        logger.info("rota empty, no login")
    logger.info("Rota downloaded")
    return rota
    

@get_rota_router.get("/api/test")
async def get_test(_o6_session: Optional[str] = Cookie(None), account_credentials: Optional[str] = Cookie(None)):
    cookies = {"_o6_session": _o6_session,"account_credentials": account_credentials}
    success = await test_is_logged_in(cookies=cookies)
    return {"message": f"test success: {success}"}
