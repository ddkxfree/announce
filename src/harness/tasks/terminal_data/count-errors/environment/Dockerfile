FROM python:3.12-slim
WORKDIR /app
COPY make_log.py /tmp/make_log.py
RUN python /tmp/make_log.py /app/logs/server.log && rm /tmp/make_log.py
