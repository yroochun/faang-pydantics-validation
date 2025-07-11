from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv


app = FastAPI()

origins = [
    "*"
]

load_dotenv()


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)




@app.get("/")
def root():
    return {"message": "Data Portal API"}



class User(BaseModel):
    name: str
    age: int

    class Config:
        strict = True
        frozen = True
        extra = "forbid"

# use enum/literal to restrict options for columns
# model validation
# deserialise json object to know if it is valid or not