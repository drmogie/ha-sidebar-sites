# Sidebar Proxy Home Assistant add-on.
# A small Python reverse proxy. Nothing else is installed.
FROM python:3.13-alpine

RUN pip install --no-cache-dir "aiohttp>=3.10"

COPY proxy.py /app/proxy.py

ENTRYPOINT ["python3", "-u", "/app/proxy.py"]
