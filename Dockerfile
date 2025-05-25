FROM python:3.11-slim

WORKDIR /app

# Установить зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем только исходный код (без конфигов, базы и шаблонов)
COPY main.py tracker.py db_handlers.py db_viewer.py ./

# Папки для монтирования
RUN mkdir /config /data /templates

# Flask ищет шаблоны по умолчанию в ./templates
ENV FLASK_APP=main.py

CMD ["python", "main.py"]