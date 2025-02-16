FROM python:3.12.8-alpine3.21 AS prod

WORKDIR /app/

RUN python3 -m venv /opt/venv && \
    mkdir ./servicesCreate a GitHub Actions workflow for CI.

ENV PATH="/opt/venv/bin:$PATH"

COPY *.py .env requirements.txt /app/

COPY services /app/services

RUN pip install --no-cache-dir -r ./requirements.txt

USER nobody

CMD ["python3", "./app.py"]

FROM prod AS dev

USER root

RUN apk add --no-cache curl=8.11.1-r0

USER nobody
