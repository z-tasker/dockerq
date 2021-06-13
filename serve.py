#!/usr/bin/env python3
from __future__ import annotations
import argparse
import os
import sys
import json
import logging
import ssl
from pathlib import Path

import aiodocker
import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.authentication import requires
from starlette.background import BackgroundTasks
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, Mount
from starlette.templating import Jinja2Templates

from middlewear import get_middlewear
from log import get_logger

MAX_DOCKER_CONCURRENCY = int(os.getenv("DOCKERQ_MAX_CONCURRENCY", 2))


async def home(request: Request) -> HTMLResponse:
    return HTMLResponse("<html><body>Home</body></html>")


def canonicalize_name(name: str) -> str:
    return f"dockerq-{name}"


@requires("authenticated")
async def show(request: Request) -> JSONResponse:
    docker = aiodocker.Docker()
    containers = await docker.containers.list()
    await docker.close()
    return JSONResponse({"containers": [container.id for container in containers]})


@requires("authenticated")
async def submit(request: Request) -> JSONResponse:

    docker = aiodocker.Docker()
    body = await request.json()

    tasks = BackgroundTasks()
    tasks.add_task(docker.close)

    try:
        existing_container = await docker.containers.get(
            canonicalize_name(body["name"])
        )
        status = await existing_container.show()
        if not status["State"]["Running"]:
            request.app.state.log.debug(
                f"deleting stopped container {existing_container.id} ({body['name']})"
            )
            await existing_container.delete()
    except aiodocker.exceptions.DockerError as exc:
        if exc.status != 404:
            return JSONResponse(
                {"message": exc.message}, status_code=exc.status, background=tasks
            )

    existing_containers = await docker.containers.list()
    running_containers = 0
    for container in existing_containers:
        status = await container.show()
        if status["State"]["Running"]:
            running_containers += 1

    if running_containers >= MAX_DOCKER_CONCURRENCY:
        return JSONResponse(
            {
                "message": f"Cannot accept a new task, there are already {running_containers} containers running"
            },
            status_code=503,
            background=tasks,
        )

    try:
        container = await docker.containers.create(
            config={
                "Image": body["image"],
                "Cmd": body["cmd"],
                "Env": [f"{key}={val}" for key, val in body["env"].items()]
                if "env" in body
                else None,
                "HostConfig": {"ShmSize": 2000000000},
            },
            name=canonicalize_name(body["name"]),
        )
    except aiodocker.exceptions.DockerError as exc:
        return JSONResponse(
            {"message": exc.message}, status_code=exc.status, background=tasks
        )

    try:
        await container.start()
    except aiodocker.exceptions.DockerError as exc:
        return JSONResponse(
            {"message": exc.message}, status_code=exc.status, background=tasks
        )

    return JSONResponse(
        {"container": container.id, "message": "container started"},
        status_code=200,
        background=tasks,
    )


@requires("authenticated")
async def status(request: Request) -> JSONResponse:
    docker = aiodocker.Docker()

    tasks = BackgroundTasks()
    tasks.add_task(docker.close)

    try:
        container = await docker.containers.get(
            canonicalize_name(request.query_params["name"])
        )
        status = await container.show()
        return JSONResponse(
            {
                "state": status["State"],
                "logs": await container.log(stdout=True, stderr=True),
            },
            status_code=200,
            background=tasks,
        )
    except aiodocker.exceptions.DockerError as exc:
        return JSONResponse(exc.message, status_code=exc.status, background=tasks)


@requires("authenticated")
async def flush(request: Request) -> JSONResponse:
    docker = aiodocker.Docker()

    tasks = BackgroundTasks()
    tasks.add_task(docker.close)

    try:
        container = await docker.containers.get(
            canonicalize_name(request.query_params["name"])
        )
        status = await container.show()
        if status["State"]["Running"]:
            return JSONResponse(
                {"state": status["State"], "message": "container still running"},
                status_code=200,
                background=tasks,
            )
        else:
            return JSONResponse(
                {
                    "state": status["State"],
                    "message": f"container exited {status['State']['ExitCode']}",
                    "logs": await container.log(stdout=True, stderr=True),
                },
                status_code=200,
                background=tasks,
            )
    except aiodocker.exceptions.DockerError as exc:
        return JSONResponse(exc.message, status_code=exc.status, background=tasks)


async def cleanup_stopped_containers() -> None:
    log = get_logger("cleanup_stopped_containers")
    log.debug("running cleanup background process")

    docker = aiodocker.Docker()
    containers = await docker.containers.list(all=1)
    for container in containers:
        status = await container.show()
        if not status["Name"].startswith("/dockerq-"):
            continue
        if status["State"]["Running"]:
            continue
        else:
            exit_code = status["State"]["ExitCode"]
            logs = await container.log(stdout=True, stderr=True)
            if exit_code != 0:
                log.error(f"{status['Name']} container exited {exit_code}")
                log.error("".join(logs))
            else:
                log.debug(f"{status['Name']} container exited 0")
                log.debug("".join(logs))
            await container.delete()

    await docker.close()


async def start_background_processes() -> None:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(cleanup_stopped_containers, "interval", minutes=1)
    scheduler.start()
    log = get_logger("start_background_processes")
    log.info("intialized scheduler")
    log.info(scheduler.get_jobs())


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()

    parser.add_argument("--dev", action="store_true")

    return parser


def main() -> Optional[Starlette]:
    """Prepare Starlette Application and run in server event loop"""

    args = get_parser().parse_args()

    routes = [
        Route("/", home),
        Route("/show", show),
        Route("/status", status),
        Route("/flush", flush),
        Route("/submit", submit, methods=["POST"]),
    ]

    app = Starlette(
        middleware=get_middlewear(),
        routes=routes,
        on_startup=[start_background_processes],
    )
    app.state.templates = Jinja2Templates(directory="templates")
    app.state.log = get_logger("app")

    ## add elasticsearch client and s3 client to app.state
    # elasticsearch_client = get_elasticsearch_client()
    # s3_client = get_s3_client()

    # app.state.elasticsearch_client = elasticsearch_client
    # app.state.s3_client = s3_client

    if args.dev:
        uvicorn.run(app, host="127.0.0.1", port=8080, proxy_headers=True)
    else:
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8884,
            proxy_headers=True,
            ssl_keyfile=os.getenv("DOCKERQ_SSL_KEYFILE"),
            ssl_certfile=os.getenv("DOCKERQ_SSL_CERTFILE"),
            ssl_ca_certs=os.getenv("DOCKERQ_SSL_CA_CERTS"),
            ssl_cert_reqs=ssl.CERT_REQUIRED,
        )

    return app


if __name__ == "__main__":
    load_dotenv()
    main()
