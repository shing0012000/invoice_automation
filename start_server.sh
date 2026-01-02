#!/bin/bash
# Kill any existing process on port 8000
lsof -ti:8000 | xargs kill -9 2>/dev/null

# Activate conda environment and start server
source /opt/anaconda3/etc/profile.d/conda.sh
conda activate acctapp
cd /Users/takshingchan/Desktop/AI_ML_work/Jobs_tasks/Dev_AcctApp/invoice_automation
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
