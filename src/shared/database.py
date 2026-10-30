import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
POOL_SIZE = int(os.getenv("POOL_SIZE", "10"))
MAX_POOL_SIZE = int(os.getenv("MAX_POOL_SIZE", "15"))
