{
  "$schema": "https://railway.app/railway.schema.json",
  "build": { "builder": "NIXPACKS" },
  "deploy": {
    "startCommand": "gunicorn web.app:app --workers 2 --threads 8 --timeout 180",
    "restartPolicyType": "ON_FAILURE",
    "healthcheckPath": "/healthz"
  }
}
