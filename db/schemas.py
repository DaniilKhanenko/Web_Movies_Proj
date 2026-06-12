from pydantic import BaseModel


class AuthData(BaseModel):
    username: str
    password: str


class RoomCreateData(BaseModel):
    title: str = "Комната"
    password: str
    movie_id: str
    room_id: str = ""


class RoomJoinData(BaseModel):
    password: str
