FROM python:3.11-slim

WORKDIR /app

# Установим зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходники и шаблоны
COPY . .

# Создадим папки для данных и логов (если не монтируются)
RUN mkdir -p /data /config /templates

# Открываем порт (по умолчанию 8080)
EXPOSE 8080

CMD ["python", "main.py"]