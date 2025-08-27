from datetime import datetime

def check_policy_status(start_date: str, end_date: str):
    now = datetime.utcnow()
    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)
    return start <= now <= end

