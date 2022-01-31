from fastapi import Depends, Response, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter
from pydantic import BaseModel
import aiohttp, asyncio
from loguru import logger

from env.secret import thr_login_url, three_login, test_url

login_router = APIRouter()


class LoginModel(BaseModel):
    username: str
    password: str


tr_login_form_model = {
    "utf8": "✓",
    "authenticity_token": None,
    "account_session[username]": None,
    "account_session[password]": None,
    "commit": "Log In",
}


@login_router.post("/api/login")
async def login(login_data: LoginModel, response: Response):
    logger.info(f"Login attempt: {login_data.username}")
    jar = await get_cookies(login_data)
    if not jar:
        return {"message": "login failed"}  # send login error to FE
    valid = await test_is_logged_in(cookie_jar=jar)
    if not valid:
        return {"message": "cookies invalid/expired"}
    content = {"message": "login success"}
    response = JSONResponse(content=content)
    response.headers.append("access-control-expose-headers", "Set-Cookie")
    for c in jar:
        # response.set_cookie(
        #     key=c.key,
        #     value=c.value,
        #     httponly=True,
        #     secure=True,
        #     samesite=None,
        # )
        response.headers.append("Set-Cookie", f"{c.key}={c.value}; SameSite=None; Secure")
    logger.info(f"Logged in: {login_data.username}")
    return response
    # send cookies to FE/browser, assign user as LoginModel.username


async def get_cookies(login_data: LoginModel) -> aiohttp.CookieJar:
    # data = await get_data()  # for full form model
    data = tr_login_form_model
    if not data:
        return
    data["account_session[username]"] = login_data.username
    data["account_session[password]"] = login_data.password
    async with aiohttp.ClientSession() as session:
        await session.post(thr_login_url, data=data)
        jar = session.cookie_jar
        for c in jar:
            if c.key == "account_credentials":
                return jar
            # print(c.key, c.value)
    logger.info("account_credentials not in CookieJar, invalid login")
    raise HTTPException(status_code=401, detail="Invalid login")


async def test_is_logged_in(cookies = None,
    cookie_jar: aiohttp.CookieJar = None,
) -> bool:  # TODO pull cookiejar from FE

    # test with cookies
    if not cookie_jar:
        async with aiohttp.ClientSession(cookies=cookies) as session:
            res = await session.get(test_url, allow_redirects=False)
            status = res.status
            if status != 200:
                logger.info("Test login fail (cookies)")
                raise HTTPException(status_code=401, detail="Invalid login")
                return
            logger.info("Test login success (cookies)")
            return True

    # test with cookie jar
    else:
        async with aiohttp.ClientSession(cookie_jar=cookie_jar) as session:
            res = await session.get(test_url, allow_redirects=False)
            status = res.status
            if status != 200:
                logger.info("Test login fail (cookie jar)")
                raise HTTPException(status_code=401, detail="Invalid login")
                return
            logger.info("Test login success (cookie jar)")
            return True
