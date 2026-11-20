FROM python:3.14-alpine@sha256:76c65fc8c52c4d375e958298d9f66198b8fb6b06416c0e5500bf710c19cbaa77 AS prod

WORKDIR /app/

RUN python3 -m venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r ./requirements.txt

COPY src/ /app/src/
COPY .env /app/.env

USER nobody

CMD ["python3", "./src/app.py"]
