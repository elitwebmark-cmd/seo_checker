web: gunicorn app:app --workers 2 --threads 4 --timeout 600 --graceful-timeout 30 --access-logfile - --error-logfile -
worker: python -u bot.py
