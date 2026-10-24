"""Start the New Haven Rent Desk.

    .venv/Scripts/python.exe run.py          (Windows)
    .venv/bin/python run.py                  (macOS / Linux)

Then open http://127.0.0.1:8000
"""
import uvicorn

if __name__ == "__main__":
    print("New Haven Rent Desk -> http://127.0.0.1:8000")
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
