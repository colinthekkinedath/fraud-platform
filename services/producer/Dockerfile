FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .


ENV PYTHONUNBUFFERED=1          
ENV TARGET_TPS=500
ENV KAFKA_BOOTSTRAP=kafka:9092

EXPOSE 8001

CMD ["python", "app.py"]    