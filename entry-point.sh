#!/bin/bash -e
/home/admin/.local/bin/gunicorn -w 4 -k uvicorn.workers.UvicornWorker --access-logfile - 'serve:main()' -b 0.0.0.0:8080
