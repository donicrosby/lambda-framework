"""FastAPI module."""

from fastapi import FastAPI
from mangum import Mangum

APP: FastAPI = FastAPI()
HANDLER: Mangum = Mangum(APP)
