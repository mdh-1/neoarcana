from loguru import logger
from dotenv import dotenv_values
logger.add("logs/tarot_reader.log", rotation="1 MB", level="DEBUG", format="{time} {level} {message}", backtrace=True, diagnose=True)



keys = dotenv_values(".env")
RANDOM_API_KEY = keys["RANDOM_API_KEY"]
MISTRAL_API_KEY =keys["MISTRAL_API_KEY"]
DEEPSEEK_API_KEY = keys["DEEPSEEK_API_KEY"]
GROK_API_KEY = keys["GROK_API_KEY"]

