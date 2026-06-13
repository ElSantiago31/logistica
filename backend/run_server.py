"""Launch uvicorn server with correct working directory."""
import os, sys

os.chdir(r"c:\Users\Karen\Downloads\logistica\backend")
sys.path.insert(0, os.getcwd())

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
