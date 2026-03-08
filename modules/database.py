import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column
from sqlalchemy.types import String, Integer, DateTime, Boolean
from datetime import datetime

load_dotenv()
DB_URL = os.getenv('SQL_URL')
engine = create_engine(DB_URL, pool_pre_ping=True, pool_recycle=300)

sessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    line_user_id = Column(String, primary_key=True, index=True)  # LINE user_id を主キーに（提案6: マルチユーザー対応）
    token = Column(String, nullable=True)
    is_approved = Column(Boolean, default=False, nullable=False)
    drive_folder_id = Column(String, nullable=True)    # per-user Google Drive folder (R02)
    spreadsheet_id = Column(String, nullable=True)     # per-user Google Spreadsheet (R02)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OAuthNonce(Base):
    __tablename__ = "oauth_nonces"
    id = Column(Integer, primary_key=True)
    nonce = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)