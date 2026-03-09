from fastapi import FastAPI

app = FastAPI(title="AGLMS API")

@app.get("/")
def root():
    return {"message": "AGLMS API is running"}

@app.get("/health")
def health():
    return {"status": "ok", "service": "AGLMS API", "version": "0.1.0"}