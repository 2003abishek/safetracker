from sqlalchemy import create_engine, Column, String, Text, DateTime, Float, Integer, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime, timedelta
import uuid
import streamlit as st
import os

Base = declarative_base()

class TrackingSession(Base):
    __tablename__ = 'tracking_sessions'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sender_phone = Column(String(20), nullable=False)
    recipient_phone = Column(String(20), nullable=False)
    message = Column(Text, nullable=True)
    status = Column(String(20), default='pending')
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    
    locations = relationship("LocationUpdate", back_populates="session", cascade="all, delete-orphan")

class LocationUpdate(Base):
    __tablename__ = 'location_updates'
    
    id = Column(Integer, primary_key=True)
    session_id = Column(String(36), ForeignKey('tracking_sessions.id'), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    accuracy = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    address = Column(Text, nullable=True)
    
    session = relationship("TrackingSession", back_populates="locations")

class Database:
    def __init__(self):
        # Use Streamlit secrets for database URL
        self.database_url = st.secrets.get('DATABASE_URL', 'sqlite:///safetrack.db')
        self.engine = create_engine(self.database_url)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        
    def init_db(self):
        Base.metadata.create_all(bind=self.engine)
    
    def get_session(self):
        return self.SessionLocal()

# Initialize database
db = Database()
db.init_db()
