FROM python:3.12.8-alpine3.21

WORKDIR /app/

RUN python3 -m venv /opt/venv && \
    mkdir ./services

ENV PATH="/opt/venv/bin:$PATH"

COPY *.py .env requirements.txt /app/

COPY services /app/services

RUN pip install --no-cache-dir -r ./requirements.txt

CMD ["python3", "./app.py"]
