FROM python:3.10-slim

WORKDIR /app

COPY server.py .

EXPOSE 8574

CMD ["python", "server.py"]