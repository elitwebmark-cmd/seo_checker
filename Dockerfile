FROM python:3.11-slim

# Системні бібліотеки для WeasyPrint (рендер PDF) + шрифти з кирилицею.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        libffi8 \
        libfontconfig1 \
        fontconfig \
        shared-mime-info \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Веб (gunicorn). Воркер-бот запускається через Custom Start Command сервіса:
#   python -u bot.py
ENV PORT=8080
# 2 воркери: поки один зайнятий фоновою обробкою/manus, другий миттєво відповідає
# вебхуку HubSpot (перша спроба HubSpot таймаутила, коли єдиний воркер був зайнятий).
# access/error логи в stdout — щоб у Railway було видно кожен вхідний запит.
CMD gunicorn app:app --workers 2 --threads 4 --timeout 600 --graceful-timeout 30 --access-logfile - --error-logfile - --bind 0.0.0.0:${PORT:-8080}
