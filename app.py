import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import folium
from streamlit_folium import folium_static
from database import db, TrackingSession, LocationUpdate
from sms_service import sms_service
import time

# Page configuration
st.set_page_config(
    page_title="SafeTrack - Location Tracking",
    page_icon="📍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'current_tracking_id' not in st.session_state:
    st.session_state.current_tracking_id = None
if 'tracking_sessions' not in st.session_state:
    st.session_state.tracking_sessions = []

def init_session_state():
    """Initialize session state with database data"""
    session = db.get_session()
    try:
        tracking_sessions = session.query(TrackingSession).order_by(TrackingSession.created_at.desc()).all()
        st.session_state.tracking_sessions = tracking_sessions
    finally:
        session.close()

def send_tracking_request(sender_phone, recipient_phone, custom_message):
    """Send tracking request via SMS"""
    session = db.get_session()
    try:
        # Create tracking session
        tracking_session = TrackingSession(
            sender_phone=sender_phone,
            recipient_phone=recipient_phone,
            message=custom_message,
            expires_at=datetime.utcnow() + timedelta(hours=24)
        )
        session.add(tracking_session)
        session.commit()
        
        # Send SMS
        sms_result = sms_service.send_tracking_request(
            recipient_phone, 
            tracking_session.id, 
            custom_message
        )
        
        if sms_result['success']:
            st.session_state.current_tracking_id = tracking_session.id
            init_session_state()  # Refresh session list
            return {
                'success': True,
                'tracking_id': tracking_session.id,
                'tracking_url': sms_result.get('tracking_url', '')
            }
        else:
            # Still return success for database entry, but show SMS warning
            return {
                'success': True,
                'tracking_id': tracking_session.id,
                'sms_sent': False,
                'error': sms_result.get('error', 'Unknown error'),
                'debug_url': sms_result.get('debug_url', '')
            }
            
    except Exception as e:
        session.rollback()
        return {'success': False, 'error': str(e)}
    finally:
        session.close()

def get_tracking_session(tracking_id):
    """Get tracking session by ID"""
    session = db.get_session()
    try:
        return session.query(TrackingSession).filter(TrackingSession.id == tracking_id).first()
    finally:
        session.close()

def get_locations(tracking_id):
    """Get all locations for a tracking session"""
    session = db.get_session()
    try:
        locations = session.query(LocationUpdate).filter(
            LocationUpdate.session_id == tracking_id
        ).order_by(LocationUpdate.timestamp.asc()).all()
        return locations
    finally:
        session.close()

def save_location(tracking_id, latitude, longitude, accuracy=None):
    """Save location update"""
    session = db.get_session()
    try:
        tracking_session = session.query(TrackingSession).filter(TrackingSession.id == tracking_id).first()
        if not tracking_session:
            return {'success': False, 'error': 'Invalid tracking session'}
        
        # Update session status
        if tracking_session.status == 'pending':
            tracking_session.status = 'active'
        
        # Save location
        location_update = LocationUpdate(
            session_id=tracking_id,
            latitude=latitude,
            longitude=longitude,
            accuracy=accuracy
        )
        session.add(location_update)
        session.commit()
        
        return {'success': True}
        
    except Exception as e:
        session.rollback()
        return {'success': False, 'error': str(e)}
    finally:
        session.close()

def create_map(locations):
    """Create Folium map with location markers"""
    if not locations:
        # Default map centered on world
        m = folium.Map(location=[20, 0], zoom_start=2)
        return m
    
    # Center map on latest location
    latest_loc = locations[-1]
    m = folium.Map(location=[latest_loc.latitude, latest_loc.longitude], zoom_start=15)
    
    # Add markers for all locations
    for i, loc in enumerate(locations):
        folium.Marker(
            [loc.latitude, loc.longitude],
            popup=f"Location {i+1}<br>Time: {loc.timestamp.strftime('%H:%M:%S')}",
            tooltip=f"Location {i+1}",
            icon=folium.Icon(color='red' if i == len(locations)-1 else 'blue')
        ).add_to(m)
    
    # Add line connecting locations
    if len(locations) > 1:
        locations_list = [[loc.latitude, loc.longitude] for loc in locations]
        folium.PolyLine(locations_list, color="blue", weight=2.5, opacity=1).add_to(m)
    
    return m

def main():
    # Sidebar
    st.sidebar.title("📍 SafeTrack")
    st.sidebar.markdown("### Navigation")
    
    page = st.sidebar.radio("Go to", ["Send Tracking Request", "View Tracking Sessions", "Share Location"])
    
    # Check for tracking ID in URL parameters
    query_params = st.experimental_get_query_params()
    tracking_id_from_url = query_params.get('tracking_id', [None])[0]
    
    if tracking_id_from_url and page != "Share Location":
        st.sidebar.info(f"Tracking session detected: {tracking_id_from_url[:8]}...")
        if st.sidebar.button("Go to Share Location"):
            page = "Share Location"
            st.session_state.share_tracking_id = tracking_id_from_url
    
    # Initialize session state
    init_session_state()
    
    if page == "Send Tracking Request":
        show_send_request_page()
    elif page == "View Tracking Sessions":
        show_tracking_sessions_page()
    elif page == "Share Location":
        show_share_location_page()

def show_send_request_page():
    st.title("📱 Send Location Tracking Request")
    
    st.markdown("""
    Send an SMS to request someone's current location. The recipient will receive 
    a link to share their location securely.
    """)
    
    with st.form("tracking_request_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            sender_phone = st.text_input("Your Phone Number (optional)", placeholder="+1234567890")
            recipient_phone = st.text_input("Recipient's Phone Number*", placeholder="+1234567890")
        
        with col2:
            custom_message = st.text_area(
                "Message to send",
                value="Please share your location for safety reasons.",
                height=100
            )
        
        submitted = st.form_submit_button("Send Tracking Request")
        
        if submitted:
            if not recipient_phone:
                st.error("Please enter recipient's phone number")
                return
            
            with st.spinner("Sending tracking request..."):
                result = send_tracking_request(sender_phone, recipient_phone, custom_message)
                
                if result['success']:
                    st.success("✅ Tracking request sent successfully!")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.info(f"**Tracking ID:** {result['tracking_id']}")
                    
                    with col2:
                        if result.get('sms_sent', True):
                            st.info("📱 SMS sent to recipient")
                        else:
                            st.warning("⚠️ SMS not sent (Twilio not configured)")
                            if result.get('debug_url'):
                                st.code(result['debug_url'])
                    
                    # Show quick actions
                    st.markdown("### Next Steps")
                    st.markdown(f"""
                    - **View tracking session:** Go to 'View Tracking Sessions' in the sidebar
                    - **Share this session:** Tracking ID: `{result['tracking_id']}`
                    - **Wait for location updates:** The recipient will share their location via the link
                    """)
                    
                else:
                    st.error(f"Failed to send tracking request: {result.get('error', 'Unknown error')}")

def show_tracking_sessions_page():
    st.title("📊 Tracking Sessions")
    
    if not st.session_state.tracking_sessions:
        st.info("No tracking sessions yet. Send a tracking request to get started!")
        return
    
    # Session selection
    session_options = {f"{s.id[:8]}... - {s.recipient_phone} - {s.created_at.strftime('%Y-%m-%d %H:%M')}": s.id 
                      for s in st.session_state.tracking_sessions}
    
    selected_session_label = st.selectbox(
        "Select Tracking Session",
        options=list(session_options.keys()),
        index=0
    )
    
    tracking_id = session_options[selected_session_label]
    tracking_session = get_tracking_session(tracking_id)
    locations = get_locations(tracking_id)
    
    if tracking_session:
        # Session info
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Recipient", tracking_session.recipient_phone)
        with col2:
            st.metric("Status", tracking_session.status)
        with col3:
            st.metric("Locations Received", len(locations))
        
        # Map and locations
        if locations:
            st.subheader("📍 Location Map")
            map_obj = create_map(locations)
            folium_static(map_obj, width=800, height=400)
            
            # Location history
            st.subheader("📋 Location History")
            locations_data = []
            for loc in locations:
                locations_data.append({
                    'Timestamp': loc.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    'Latitude': loc.latitude,
                    'Longitude': loc.longitude,
                    'Accuracy': f"{loc.accuracy}m" if loc.accuracy else "N/A"
                })
            
            df = pd.DataFrame(locations_data)
            st.dataframe(df, use_container_width=True)
            
            # Export options
            col1, col2 = st.columns(2)
            with col1:
                csv = df.to_csv(index=False)
                st.download_button(
                    label="Download CSV",
                    data=csv,
                    file_name=f"locations_{tracking_id[:8]}.csv",
                    mime="text/csv"
                )
            
        else:
            st.info("No locations received yet. Waiting for recipient to share their location.")
            
            # Show tracking URL for sharing
            tracking_url = f"{sms_service.server_url}/?tracking_id={tracking_id}"
            st.text_input("Share this URL with recipient:", tracking_url)

def show_share_location_page():
    st.title("📍 Share Your Location")
    
    # Get tracking ID from URL or manual input
    tracking_id = None
    
    # Check if tracking ID came from URL
    if 'share_tracking_id' in st.session_state:
        tracking_id = st.session_state.share_tracking_id
        st.success(f"Tracking session detected: {tracking_id[:8]}...")
    else:
        query_params = st.experimental_get_query_params()
        tracking_id_from_url = query_params.get('tracking_id', [None])[0]
        if tracking_id_from_url:
            tracking_id = tracking_id_from_url
            st.success(f"Tracking session detected: {tracking_id[:8]}...")
    
    # Manual tracking ID input
    if not tracking_id:
        tracking_id = st.text_input("Enter Tracking ID", placeholder="Paste the tracking ID from your SMS")
    
    if tracking_id:
        # Verify tracking session exists
        tracking_session = get_tracking_session(tracking_id)
        if not tracking_session:
            st.error("Invalid tracking ID. Please check and try again.")
            return
        
        if tracking_session.status == 'expired':
            st.error("This tracking link has expired.")
            return
        
        st.info(f"**Recipient:** {tracking_session.recipient_phone}")
        if tracking_session.message:
            st.info(f"**Message:** {tracking_session.message}")
        
        st.markdown("---")
        st.subheader("Share Your Current Location")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            if st.button("📍 Share My Current Location", type="primary", use_container_width=True):
                share_location(tracking_id)
        
        with col2:
            if st.button("🚫 Don't Share", use_container_width=True):
                st.info("Location sharing cancelled.")
        
        # Show previous locations if any
        existing_locations = get_locations(tracking_id)
        if existing_locations:
            st.subheader("Your Shared Locations")
            map_obj = create_map(existing_locations)
            folium_static(map_obj, width=700, height=300)
            
            for i, loc in enumerate(reversed(existing_locations[-3:]), 1):
                st.write(f"**Location {i}:** {loc.timestamp.strftime('%H:%M:%S')} - "
                        f"Lat: {loc.latitude:.6f}, Lng: {loc.longitude:.6f}")

def share_location(tracking_id):
    """Handle location sharing using Streamlit's experimental feature"""
    try:
        # Use Streamlit's experimental geolocation feature
        with st.spinner("Getting your location..."):
            # This is a simplified version - in a real app, you might use JavaScript integration
            # or a dedicated location sharing service
            
            # For demo purposes, we'll simulate location or use a fallback
            st.warning("""
            **Note:** Streamlit doesn't have built-in geolocation in the main version yet.
            
            In a production app, you would:
            1. Use JavaScript integration via components
            2. Use a mobile-responsive web app
            3. Integrate with native mobile capabilities
            
            For this demo, we'll simulate location data.
            """)
            
            # Simulate location (in real app, get from browser geolocation API)
            import random
            simulated_lat = 40.7128 + random.uniform(-0.01, 0.01)  # Around NYC
            simulated_lng = -74.0060 + random.uniform(-0.01, 0.01)
            accuracy = random.uniform(5, 50)
            
            result = save_location(tracking_id, simulated_lat, simulated_lng, accuracy)
            
            if result['success']:
                st.success("✅ Location shared successfully!")
                st.balloons()
                
                # Show the shared location on a map
                import folium
                from streamlit_folium import folium_static
                
                m = folium.Map(location=[simulated_lat, simulated_lng], zoom_start=15)
                folium.Marker(
                    [simulated_lat, simulated_lng],
                    popup="Your shared location",
                    tooltip="Your location",
                    icon=folium.Icon(color='green')
                ).add_to(m)
                
                folium_static(m, width=600, height=400)
                
                st.write(f"**Latitude:** {simulated_lat:.6f}")
                st.write(f"**Longitude:** {simulated_lng:.6f}")
                st.write(f"**Accuracy:** ~{accuracy:.0f} meters")
                
            else:
                st.error(f"Failed to share location: {result.get('error', 'Unknown error')}")
                
    except Exception as e:
        st.error(f"Error getting location: {str(e)}")

if __name__ == "__main__":
    main()