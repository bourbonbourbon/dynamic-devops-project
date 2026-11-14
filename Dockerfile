FROM python:3.14-alpine AS prod

WORKDIR /app/

RUN python3 -m venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r ./requirements.txt

COPY src/ /app/src/
COPY .env /app/.env

USER nobody

CMD ["python3", "./src/app.py"]
