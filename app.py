import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import folium
from streamlit_folium import folium_static
from database import db, TrackingSession, LocationUpdate
from sms_service import sms_service
import time
import os
import random

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
    
    # Show deployment info
    st.sidebar.markdown("**Cloud Deployment** ☁️")
    
    st.sidebar.markdown("### Navigation")
    page = st.sidebar.radio("Go to", ["Send Tracking Request", "View Tracking Sessions", "Share Location"])
    
    # Check for tracking ID in URL parameters
    try:
        query_params = st.experimental_get_query_params()
        tracking_id_from_url = query_params.get('tracking_id', [None])[0]
    except:
        tracking_id_from_url = None
    
    if tracking_id_from_url and page != "Share Location":
        st.sidebar.info(f"Tracking session detected!")
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
    
    # Show deployment status
    if not sms_service.is_configured:
        st.info("""
        **🌐 Streamlit Cloud Edition**
        - Manual URL sharing enabled
        - Copy and share links via any messaging app
        - Full location tracking functionality
        """)
    
    st.markdown("""
    Create a secure location tracking request. Share the generated link with anyone to request their current location.
    """)
    
    with st.form("tracking_request_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            sender_name = st.text_input("Your Name (optional)", placeholder="Your Name")
            recipient_name = st.text_input("Recipient Name*", placeholder="Recipient Name")
            
        with col2:
            custom_message = st.text_area(
                "Message to include",
                value="Please share your location for safety reasons.",
                height=100,
                help="This message will be included in the sharing link"
            )
        
        submitted = st.form_submit_button("Create Tracking Request")
        
        if submitted:
            if not recipient_name:
                st.error("Please enter recipient name")
                return
            
            with st.spinner("Creating tracking request..."):
                # Use names instead of phone numbers for cloud version
                sender_phone = sender_name or "Anonymous"
                recipient_phone = recipient_name
                
                result = send_tracking_request(sender_phone, recipient_phone, custom_message)
                
                if result['success']:
                    st.success("✅ Tracking request created successfully!")
                    
                    tracking_id = result['tracking_id']
                    
                    # Display tracking information
                    col1, col2 = st.columns(2)
                    with col1:
                        st.info(f"**Tracking ID:** `{tracking_id}`")
                    with col2:
                        if result.get('sms_sent', True):
                            st.success("📱 SMS sent to recipient")
                        else:
                            st.warning("📧 Manual sharing required")
                    
                    # Show shareable URL prominently
                    tracking_url = result.get('tracking_url') or f"{sms_service.server_url}/?tracking_id={tracking_id}"
                    
                    st.subheader("🔗 Share This Link")
                    
                    # URL display with copy functionality
                    st.code(tracking_url, language="text")
                    
                    # Copy button
                    st.download_button(
                        "📋 Copy Link to Clipboard",
                        data=tracking_url,
                        file_name=f"tracking_link_{tracking_id[:8]}.txt",
                        mime="text/plain",
                        use_container_width=True
                    )
                    
                    # QR Code for easy sharing
                    try:
                        import qrcode
                        from io import BytesIO
                        
                        qr = qrcode.QRCode(
                            version=1,
                            error_correction=qrcode.constants.ERROR_CORRECT_L,
                            box_size=10,
                            border=4,
                        )
                        qr.add_data(tracking_url)
                        qr.make(fit=True)
                        
                        img = qr.make_image(fill_color="black", back_color="white")
                        buf = BytesIO()
                        img.save(buf, format="PNG")
                        
                        st.image(buf.getvalue(), 
                                caption="📱 Scan QR Code to share location", 
                                width=200)
                    except ImportError:
                        st.info("💡 Install 'qrcode' package for QR code generation")
                    
                    # Quick actions
                    st.markdown("### 🚀 Next Steps")
                    st.markdown(f"""
                    1. **Share the link above** via WhatsApp, Email, or any messaging app
                    2. **Go to View Tracking Sessions** to monitor locations
                    3. **The recipient** will click the link and share their location
                    
                    **Tracking ID for reference:** `{tracking_id}`
                    """)
                    
                else:
                    st.error(f"Failed to create tracking request: {result.get('error', 'Unknown error')}")

def show_tracking_sessions_page():
    st.title("📊 Tracking Sessions")
    
    if not st.session_state.tracking_sessions:
        st.info("No tracking sessions yet. Create a tracking request to get started!")
        return
    
    # Session selection
    session_options = {f"{s.id[:8]}... - {s.recipient_phone} - {s.created_at.strftime('%m/%d %H:%M')}": s.id 
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
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Recipient", tracking_session.recipient_phone)
        with col2:
            status_color = "🟢" if tracking_session.status == 'active' else "🟡" if tracking_session.status == 'pending' else "🔴"
            st.metric("Status", f"{status_color} {tracking_session.status}")
        with col3:
            st.metric("Locations", len(locations))
        with col4:
            st.metric("Created", tracking_session.created_at.strftime('%m/%d %H:%M'))
        
        # Share URL section
        st.subheader("🔗 Sharing Options")
        tracking_url = f"{sms_service.server_url}/?tracking_id={tracking_id}"
        
        col1, col2 = st.columns([3, 1])
        with col1:
            st.text_input("Shareable Link:", tracking_url, key="share_url")
        with col2:
            st.download_button(
                "Copy Link",
                data=tracking_url,
                file_name="tracking_url.txt",
                mime="text/plain",
                use_container_width=True
            )
        
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
            st.subheader("💾 Export Data")
            col1, col2 = st.columns(2)
            with col1:
                csv = df.to_csv(index=False)
                st.download_button(
                    label="Download CSV",
                    data=csv,
                    file_name=f"locations_{tracking_id[:8]}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            
        else:
            st.info("📍 No locations received yet. Share the link above with the recipient and wait for them to share their location.")
            
            # Quick tutorial
            with st.expander("📖 How to use this tracking session"):
                st.markdown("""
                1. **Copy the sharing link** above
                2. **Send it** to the recipient via any messaging app
                3. **The recipient clicks the link** and shares their location
                4. **Locations will appear here** automatically
                5. **View on map** and export data as needed
                """)

def show_share_location_page():
    st.title("📍 Share Your Location")
    
    # Get tracking ID from URL or manual input
    tracking_id = None
    
    # Check if tracking ID came from URL
    if 'share_tracking_id' in st.session_state:
        tracking_id = st.session_state.share_tracking_id
        st.success(f"📲 Tracking session detected!")
    else:
        try:
            query_params = st.experimental_get_query_params()
            tracking_id_from_url = query_params.get('tracking_id', [None])[0]
            if tracking_id_from_url:
                tracking_id = tracking_id_from_url
                st.success(f"📲 Tracking session detected!")
        except:
            pass
    
    # Manual tracking ID input
    if not tracking_id:
        tracking_id = st.text_input("Enter Tracking ID", placeholder="Paste tracking ID from your link")
    
    if tracking_id:
        # Verify tracking session exists
        tracking_session = get_tracking_session(tracking_id)
        if not tracking_session:
            st.error("❌ Invalid tracking ID. Please check and try again.")
            return
        
        if tracking_session.status == 'expired':
            st.error("⏰ This tracking link has expired.")
            return
        
        # Session information
        st.info(f"**📞 Request from:** {tracking_session.recipient_phone}")
        if tracking_session.message:
            st.info(f"**💬 Message:** {tracking_session.message}")
        
        st.markdown("---")
        
        # Location sharing options
        st.subheader("📍 Share Your Location")
        
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            if st.button("📍 Share Demo Location", type="primary", use_container_width=True, 
                        help="Share a sample location for demonstration"):
                share_demo_location(tracking_id)
        
        with col2:
            if st.button("🌍 Share Random City", use_container_width=True,
                        help="Share a random major city location"):
                share_random_city_location(tracking_id)
        
        with col3:
            if st.button("🚫 Cancel", use_container_width=True):
                st.info("Location sharing cancelled.")
        
        # Show previous locations if any
        existing_locations = get_locations(tracking_id)
        if existing_locations:
            st.subheader("📍 Your Shared Locations")
            map_obj = create_map(existing_locations)
            folium_static(map_obj, width=700, height=300)
            
            st.write("**Recent Locations:**")
            for i, loc in enumerate(reversed(existing_locations[-3:]), 1):
                st.write(f"{i}. **{loc.timestamp.strftime('%H:%M:%S')}** - "
                        f"Lat: {loc.latitude:.4f}, Lng: {loc.longitude:.4f}")

def share_demo_location(tracking_id):
    """Share a demo location with realistic data"""
    try:
        with st.spinner("Getting your location..."):
            # Realistic location simulation
            cities = [
                {"name": "New York", "coords": (40.7128, -74.0060), "icon": "🗽"},
                {"name": "London", "coords": (51.5074, -0.1278), "icon": "🇬🇧"},
                {"name": "Tokyo", "coords": (35.6762, 139.6503), "icon": "🗼"},
                {"name": "Paris", "coords": (48.8566, 2.3522), "icon": "🇫🇷"},
                {"name": "Sydney", "coords": (-33.8688, 151.2093), "icon": "🇦🇺"},
            ]
            
            city = random.choice(cities)
            base_lat, base_lng = city["coords"]
            
            # Add small random offset for realism
            simulated_lat = base_lat + random.uniform(-0.005, 0.005)
            simulated_lng = base_lng + random.uniform(-0.005, 0.005)
            accuracy = random.uniform(10, 50)
            
            result = save_location(tracking_id, simulated_lat, simulated_lng, accuracy)
            
            if result['success']:
                st.success(f"✅ Location shared successfully! {city['icon']}")
                st.balloons()
                
                # Show the shared location on a map
                m = folium.Map(location=[simulated_lat, simulated_lng], zoom_start=14)
                
                folium.Marker(
                    [simulated_lat, simulated_lng],
                    popup=f"Shared Location\n{city['name']}",
                    tooltip=f"Demo: {city['name']}",
                    icon=folium.Icon(color='green', icon='info-sign')
                ).add_to(m)
                
                # Add accuracy circle
                folium.Circle(
                    location=[simulated_lat, simulated_lng],
                    radius=accuracy,
                    popup=f"Approximate Accuracy: {accuracy:.0f}m",
                    color='green',
                    fill=True,
                    fill_opacity=0.2,
                    weight=2
                ).add_to(m)
                
                folium_static(m, width=600, height=400)
                
                # Location details
                st.subheader("📍 Location Details")
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**City:** {city['name']} {city['icon']}")
                    st.write(f"**Latitude:** {simulated_lat:.6f}")
                    st.write(f"**Longitude:** {simulated_lng:.6f}")
                with col2:
                    st.write(f"**Accuracy:** ~{accuracy:.0f} meters")
                    st.write(f"**Time Shared:** {datetime.now().strftime('%H:%M:%S')}")
                    st.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d')}")
                
            else:
                st.error(f"❌ Failed to share location: {result.get('error', 'Unknown error')}")
                
    except Exception as e:
        st.error(f"❌ Error sharing location: {str(e)}")

def share_random_city_location(tracking_id):
    """Share a random major city location"""
    major_cities = [
        {"name": "New York", "coords": (40.7128, -74.0060), "country": "USA"},
        {"name": "London", "coords": (51.5074, -0.1278), "country": "UK"},
        {"name": "Tokyo", "coords": (35.6762, 139.6503), "country": "Japan"},
        {"name": "Paris", "coords": (48.8566, 2.3522), "country": "France"},
        {"name": "Dubai", "coords": (25.2048, 55.2708), "country": "UAE"},
        {"name": "Singapore", "coords": (1.3521, 103.8198), "country": "Singapore"},
        {"name": "Sydney", "coords": (-33.8688, 151.2093), "country": "Australia"},
        {"name": "Toronto", "coords": (43.6532, -79.3832), "country": "Canada"},
    ]
    
    city = random.choice(major_cities)
    lat, lng = city["coords"]
    accuracy = random.uniform(100, 500)  # Less accurate for city-level
    
    result = save_location(tracking_id, lat, lng, accuracy)
    
    if result['success']:
        st.success(f"✅ Shared {city['name']}, {city['country']} location!")
        
        m = folium.Map(location=[lat, lng], zoom_start=12)
        folium.Marker(
            [lat, lng],
            popup=f"{city['name']}, {city['country']}",
            tooltip=city['name'],
            icon=folium.Icon(color='blue', icon='cloud')
        ).add_to(m)
        
        folium_static(m, width=500, height=300)
        
        st.info(f"**{city['name']}, {city['country']}** - This is a sample location for demonstration.")

if __name__ == "__main__":
    main()
