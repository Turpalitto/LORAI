@echo off
pip install -r backend\requirements.txt
if not exist .env copy .env.example .env
python scripts\ingest_pdf.py .
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
