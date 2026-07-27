from fastapi import FastAPI
import uvicorn
from time import sleep
from tarot_reader import TarotReader
from config import logger
from pydantic import BaseModel

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from tarot_reader import ApiResponse
app = FastAPI()


origins = [
    "*",  # Allow all origins
]

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # List of allowed origins
    allow_credentials=True,  # Allow cookies/auth
    allow_methods=["*"],  # Allow all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allow all headers
)

class ReadingRequest(BaseModel):
    reading_type: str = "celtic-cross"
    query: str | None = None
    ai_backend: str = "deepseek"




@app.post("/reading")
async def reading(response: ReadingRequest):
    reading_type = response.reading_type
    model = response.ai_backend
    query = response.query
    tarot_reader = TarotReader()
    logger.info(f"Received reading request: {reading_type} with query: {query}")
    if reading_type not in ["celtic-cross", "three-card", "one-card"]:
        logger.error(f"Invalid reading type: {reading_type}")
        return JSONResponse(content={"error": "Invalid reading type"}, status_code=400)
    if reading_type == "celtic-cross":
        response = tarot_reader.get_celtic_cross_reading(query=query,model=model)
    elif reading_type == "three-card":
        response = tarot_reader.get_three_card_reading(query=query, model=model)
    elif reading_type == "one-card":
        response = tarot_reader.get_one_card_reading(query=query,model=model)
    logger.info(f"Response: {type(response)}")
    return response

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
