# Dockerfile (at project root)
FROM python:3.10-slim

WORKDIR /app

COPY mcq/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY mcq /app/mcq

WORKDIR /app/mcq
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0

CMD ["flask", "run"]


