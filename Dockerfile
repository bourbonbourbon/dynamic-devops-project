FROM alpine:3.21.2

RUN apk -U upgrade && \
    apk add --no-cache python3=3.12.8-r1

WORKDIR /app/

RUN python3 -m venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

COPY main.py .env requirements.txt ./

RUN pip install --no-cache-dir -r ./requirements.txt

CMD ["python3", "./main.py"]
