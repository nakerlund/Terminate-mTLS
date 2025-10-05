FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir influxdb-client requests

COPY app.py .

CMD ["python", "app.py"]
