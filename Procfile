web: gunicorn app:app --workers 1 --threads 8 --timeout 600 --graceful-timeout 30 --access-logfile - --error-logfile -
worker: python -u bot.py
