import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import folium
from streamlit_folium import folium_static
from database import db, TrackingSession, LocationUpdate
from sms_service import sms_service
import time
import random
import os

# Get the actual server URL for Streamlit Cloud
def get_server_url():
    try:
        # This will work on Streamlit Cloud
        return f"https://{os.environ['STREAMLIT_SERVER_URL']}"
    except:
        # Fallback for local development
        return "http://localhost:8501"

# Update sms_service to use dynamic URL
sms_service.server_url = get_server_url()

# Rest of your existing app.py code remains the same...
# [Keep all your existing functions and code]
