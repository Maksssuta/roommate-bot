# Используем официальный Python
FROM python:3.11-slim

WORKDIR /app

# Копируем зависимости и бот
COPY requirements.txt .
COPY bot.py .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Задаем команду запуска
CMD ["python", "bot.py"]

