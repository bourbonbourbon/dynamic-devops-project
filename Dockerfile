FROM alpine:3.21.2

RUN apk -U upgrade && \
    apk add --no-cache python3=3.12.8-r1 && \
    apk add --no-cache py3-dotenv=1.0.1-r1

WORKDIR /home/src

COPY main.py ./

COPY .env ./

CMD ["python3", "./main.py"]
