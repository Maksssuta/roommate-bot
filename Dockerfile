# Используем официальный Python
# Используем Python 3.11
FROM python:3.11-slim

WORKDIR /app

# Копируем зависимости и бот
COPY requirements.txt .
COPY bot.py .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Запуск бота
CMD ["python", "bot.py"]

