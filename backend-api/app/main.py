from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import files


app = FastAPI(title="Insurance Assistant Backend")

# Allow CORS for frontend (React on port 3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routes
app.include_router(files.router, prefix="/files", tags=["Files"])

@app.get("/")
def root():
    return {"message": "Insurance Assistant Backend running 🚀"}

@app.get("/")
def health_check():
    return {"status": "ok"}