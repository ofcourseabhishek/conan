"""Entry point so the API can be started from backend/ with:  uvicorn main:app --reload

The real app lives in app/main.py (Render uses app.main:app; both work).
"""

from app.main import app

__all__ = ["app"]
