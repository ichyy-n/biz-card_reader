import os
from dotenv import load_dotenv  
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column
from sqlalchemy.types import String, Integer

load_dotenv()
DB_URL = os.getenv('SQL_URL')
engine = create_engine(DB_URL)

sessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    token = Column(String)