FROM python:3.12-alpine AS prod

WORKDIR /app/

RUN python3 -m venv /opt/venv && \
    mkdir ./services

ENV PATH="/opt/venv/bin:$PATH"

COPY *.py .env requirements.txt /app/

COPY services /app/services

RUN pip install --no-cache-dir -r ./requirements.txt

USER nobody
# too much of a hassle moving this up

CMD ["python3", "./app.py"]

# FROM prod AS dev

# USER root

# RUN apk add --no-cache curl=8.12.1-r0

# USER nobody

# CMD ["curl", "-s http://localhost:8080/version"]
# probably can do nohup python3 app.py & 2>&1 1>/dev/null && curl -s http://localhost:8080/version
# but the other thing works so eh
