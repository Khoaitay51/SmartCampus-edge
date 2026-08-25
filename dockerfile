FROM python:3.13-slim

WORKDIR /app

COPY requirement.txt .

RUN pip install --no-cache-dir -r requirement.txt

COPY . .

CMD ["uvicorn", "main:app", "--reload" , "--host", "0.0.0.0", "--port", "8000"]
