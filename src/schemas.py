from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6)
'''Схема для создания нового пользователя'''

class UserUpdate(BaseModel):
    id: int
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    email: Optional[EmailStr]
    password: Optional[str] = Field(None, min_length=6)
'''Схема для обновления данных пользователя'''

class UserLogin(BaseModel):
    email: Optional[EmailStr]
    password: str = Field(..., min_length=6)
'''Схема для аутентификации пользователя'''