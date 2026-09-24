FROM python:3.11-slim

RUN pip install --no-cache-dir pytest \
    && useradd --uid 10001 --create-home --shell /usr/sbin/nologin sandbox

WORKDIR /work
ENV PYTHONDONTWRITEBYTECODE=1
COPY selftest.py /opt/indigent-selftest.py
USER 10001:10001
