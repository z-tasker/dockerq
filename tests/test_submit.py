import aiohttp
import time
import os
import asyncio
import json
from pathlib import Path
import shlex

import pytest

BASE_URL = "http://localhost:8080"


BASIC_AUTH = aiohttp.BasicAuth("pytester", os.getenv("DOCKERQ_USER_PYTESTER_PASSWORD"))

NAME = f"sleep-runner-{int(time.time())}"

@pytest.mark.asyncio
async def test_submit():
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{BASE_URL}/submit",
            json={
                "image": "busybox",
                "cmd": ["printenv"],
                "name": NAME,
                "env": {
                    "INJECTED_ENV_A": "here it is, A!",
                    "INJECTED_ENV_B": "here it is, B!??",
                },
            },
            auth=BASIC_AUTH,
        ) as response:
            print("Status:", response.status)
            print("Content-Type:", response.headers["content-type"])

            resp = await response.json()
            print("Body:", json.dumps(resp, indent=2))

@pytest.mark.asyncio
async def test_show():
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/show", auth=BASIC_AUTH) as response:
            print("Status:", response.status)
            print("Content-Type:", response.headers["content-type"])

            resp = await response.json()
            print("Body:", json.dumps(resp, indent=2))


@pytest.mark.asyncio
async def test_status():
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{BASE_URL}/status", params={"name": NAME}, auth=BASIC_AUTH
        ) as response:
            print("Status:", response.status)
            print("Content-Type:", response.headers["content-type"])

            resp = await response.json()
            print("Body:", json.dumps(resp, indent=2))


@pytest.mark.asyncio
async def test_flush():
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{BASE_URL}/flush", params={"name": NAME}, auth=BASIC_AUTH
        ) as response:
            print("Status:", response.status)
            print("Content-Type:", response.headers["content-type"])

            resp = await response.json()
            print("Body:", json.dumps(resp, indent=2))


