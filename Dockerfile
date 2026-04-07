FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# install deps
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# copy whole project
COPY . .

# run as package
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]