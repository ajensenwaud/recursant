FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir flask

COPY bank_systems.py .

EXPOSE 6000

CMD ["python", "bank_systems.py"]
