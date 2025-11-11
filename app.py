import streamlit as st
import pandas as pd
from datetime import datetime
import io
import re
import requests
import base64

st.set_page_config(
    page_title="HFC Data Correction", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.title("🌱 HFC Data Correction")
st.markdown("### Correct data errors for farmers")

# GitHub API configuration
GITHUB_OWNER = "mohammed-seid"  # Your GitHub username
GITHUB_REPO = "hfc-data-private"

@st.cache_data(ttl=3600)  # Cache for 1 hour
def load_data_from_github():
    """Load data from private GitHub repo using PAT"""
    try:
        # Get GitHub token from secrets
        github_token = st.secrets.get("github", {}).get("token")
        
        if not github_token:
            st.error("GitHub token not configured")
            return None, None
        
        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        # Load constraints data from root directory
        constraints_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/constraints.csv"
        response = requests.get(constraints_url, headers=headers)
        
        if response.status_code != 200:
            st.error(f"Failed to load constraints: {response.status_code} - {response.text}")
            return None, None
            
        constraints_content = base64.b64decode(response.json()['content']).decode('utf-8')
        constraints_df = pd.read_csv(io.StringIO(constraints_content))
        
        # Load logic data from root directory
        logic_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/logic.csv"
        response = requests.get(logic_url, headers=headers)
        
        if response.status_code != 200:
            st.error(f"Failed to load logic: {response.status_code} - {response.text}")
            return None, None
            
        logic_content = base64.b64decode(response.json()['content']).decode('utf-8')
        logic_df = pd.read_csv(io.StringIO(logic_content))
        
        st.success("✅ Data loaded from secure repository")
        return constraints_df, logic_df
        
    except Exception as e:
        st.error(f"Error loading from GitHub: {e}")
        return None, None

# Save corrections back to GitHub
def save_corrections_to_github(corrections_df):
    """Save corrections back to private GitHub repo"""
    try:
        github_token = st.secrets.get("github", {}).get("token")
        
        if not github_token:
            return False
            
        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        # Convert corrections to CSV
        csv_data = corrections_df.to_csv(index=False)
        encoded_data = base64.b64encode(csv_data.encode()).decode()
        
        # Get current file SHA (if exists)
        corrections_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/corrections.csv"
        
        # Check if file exists
        response = requests.get(corrections_url, headers=headers)
        sha = None
        if response.status_code == 200:
            sha = response.json()['sha']
        
        # Create or update file
        payload = {
            "message": f"Add corrections - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "content": encoded_data,
            "branch": "main"
        }
        
        if sha:
            payload["sha"] = sha
            
        response = requests.put(corrections_url, headers=headers, json=payload)
        return response.status_code in [200, 201]
        
    except Exception as e:
        st.error(f"Error saving to GitHub: {e}")
        return False

# Token expiry check
def check_token_expiry():
    """Check if token is valid"""
    try:
        github_token = st.secrets.get("github", {}).get("token")
        if not github_token:
            return False
            
        headers = {"Authorization": f"token {github_token}"}
        response = requests.get("https://api.github.com/user", headers=headers)
        
        if response.status_code == 401:
            st.error("🔐 Access token expired. Please contact administrator.")
            return False
        return True
    except:
        return False

# Load data with progress indicator
with st.spinner("Loading data from secure repository..."):
    if not check_token_expiry():
        st.stop()
    
    constraints_df, logic_df = load_data_from_github()

if constraints_df is None or logic_df is None:
    st.error("Could not load data from secure repository")
    st.info("Please check: 1) GitHub token is valid 2) Files exist in private repo 3) Internet connection")
    st.stop()

# Session state to track corrected errors
if 'corrected_errors' not in st.session_state:
    st.session_state.corrected_errors = set()

# ADMIN MODE TOGGLE
is_admin = st.toggle("👨‍💼 Admin Mode", help="Enable to view all collected corrections")

if is_admin:
    # Admin view remains the same but loads from GitHub
    st.header("📊 Admin Dashboard")
    
    try:
        # Try to load corrections from GitHub
        corrections_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/corrections.csv"
        headers = {"Authorization": f"token {st.secrets.github.token}"}
        response = requests.get(corrections_url, headers=headers)
        
        if response.status_code == 200:
            corrections_content = base64.b64decode(response.json()['content']).decode('utf-8')
            all_corrections = pd.read_csv(io.StringIO(corrections_content))
            
            # Quick admin stats
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Corrections", len(all_corrections))
            with col2:
                st.metric("Enumerators", all_corrections['username'].nunique())
            with col3:
                st.metric("Farmers Corrected", all_corrections['unique_id'].nunique())
            
            # Recent corrections preview
            st.subheader("Recent Corrections")
            st.dataframe(all_corrections.tail(10), use_container_width=True)
            
            # Download options
            st.subheader("Download Data")
            csv = all_corrections.to_csv(index=False)
            st.download_button(
                label="📥 Download All Corrections",
                data=csv,
                file_name=f"all_corrections_{datetime.now().strftime('%Y%m%d')}.csv",
                mime='text/csv',
                use_container_width=True
            )
            
        else:
            st.info("📭 No corrections collected yet in the repository.")
            
    except Exception as e:
        st.error(f"Error loading corrections: {e}")

else:
    # NORMAL ENUMERATOR VIEW
    if constraints_df is not None and logic_df is not None:
        # Simple user selection at top for mobile
        st.header("👤 Select Your Account")
        
        # Get unique enumerators
        constraint_enumerators = sorted(constraints_df['username'].unique())
        logic_enumerators = sorted(logic_df['username'].unique())
        all_enumerators = sorted(set(constraint_enumerators + logic_enumerators))
        
        selected_enumerator = st.selectbox(
            "Your username:",
            options=all_enumerators,
            index=0,
            label_visibility="collapsed"
        )
        
        # Filter data for selected enumerator
        enumerator_constraints = constraints_df[constraints_df['username'] == selected_enumerator]
        enumerator_logic = logic_df[logic_df['username'] == selected_enumerator]
        
        # Remove already corrected errors
        enumerator_constraints = enumerator_constraints[~enumerator_constraints.apply(
            lambda x: f"constraint_{x['unique_id']}_{x['variable']}" in st.session_state.corrected_errors, axis=1
        )]
        enumerator_logic = enumerator_logic[~enumerator_logic.apply(
            lambda x: f"logic_{x['unique_id']}_{x['variable']}" in st.session_state.corrected_errors, axis=1
        )]
        
        # Combine farmers with errors
        all_farmers_constraints = set(enumerator_constraints['unique_id'].unique()) if len(enumerator_constraints) > 0 else set()
        all_farmers_logic = set(enumerator_logic['unique_id'].unique()) if len(enumerator_logic) > 0 else set()
        all_farmers_with_errors = sorted(all_farmers_constraints.union(all_farmers_logic))
        
        # Mobile-friendly summary
        if len(all_farmers_with_errors) == 0:
            st.success("✅ All errors corrected! No pending issues.")
        else:
            # Simple stats for mobile
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Farmers to Call", len(all_farmers_with_errors))
            with col2:
                st.metric("Total Issues", len(enumerator_constraints) + len(enumerator_logic))
            
            # MOBILE-FRIENDLY CORRECTION INTERFACE
            st.header("📞 Call Farmers & Correct Errors")
            st.markdown("**Tap on a farmer below to see and correct their errors**")
            
            for farmer_id in all_farmers_with_errors:
                # Get all errors for this farmer
                farmer_constraint_errors = enumerator_constraints[enumerator_constraints['unique_id'] == farmer_id] if len(enumerator_constraints) > 0 else pd.DataFrame()
                farmer_logic_errors = enumerator_logic[enumerator_logic['unique_id'] == farmer_id] if len(enumerator_logic) > 0 else pd.DataFrame()
                
                total_errors = len(farmer_constraint_errors) + len(farmer_logic_errors)
                
                if total_errors > 0:
                    farmer_name = ""
                    phone_no = ""
                    
                    if len(farmer_constraint_errors) > 0:
                        farmer_name = farmer_constraint_errors['farmer_name'].iloc[0]
                        phone_no = farmer_constraint_errors['phone_no'].iloc[0]
                    elif len(farmer_logic_errors) > 0:
                        farmer_name = farmer_logic_errors['farmer_name'].iloc[0]
                        phone_no = farmer_logic_errors['phone_no'].iloc[0]
                    
                    # Mobile-friendly expander with phone number prominently displayed
                    with st.expander(f"👨‍🌾 {farmer_name} 📞 {phone_no} - {total_errors} issues", expanded=False):
                        
                        # Quick farmer info at top
                        st.info(f"**Farmer:** {farmer_name} | **Phone:** {phone_no} | **ID:** {farmer_id}")
                        
                        # Process constraint errors
                        if len(farmer_constraint_errors) > 0:
                            for index, error in farmer_constraint_errors.iterrows():
                                st.subheader(f"🔒 {error['variable']}")
                                
                                # Simple mobile layout
                                col1, col2 = st.columns([2, 1])
                                
                                with col1:
                                    st.write(f"**Reported:** {error['value']}")
                                    st.write(f"**Rule:** {error['constraint']}")
                                    
                                    # Get constraints
                                    constraint_text = str(error['constraint'])
                                    min_val, max_val = 0, 100000
                                    
                                    try:
                                        if 'max' in constraint_text.lower():
                                            numbers = re.findall(r'\d+', constraint_text)
                                            if numbers:
                                                max_val = int(numbers[-1])
                                        if 'min' in constraint_text.lower():
                                            numbers = re.findall(r'\d+', constraint_text)
                                            if numbers:
                                                min_val = int(numbers[-1])
                                    except:
                                        pass
                                    
                                    # Safe current value
                                    try:
                                        current_value = int(error['value'])
                                        if current_value < min_val:
                                            current_value = min_val
                                        if max_val and current_value > max_val:
                                            current_value = max_val
                                    except:
                                        current_value = min_val
                                
                                with col2:
                                    correct_value = st.number_input(
                                        "Correct value:",
                                        min_value=min_val,
                                        max_value=max_val,
                                        value=current_value,
                                        key=f"mobile_constraint_{error['unique_id']}_{error['variable']}",
                                        label_visibility="collapsed"
                                    )
                                
                                explanation = st.text_area(
                                    "Reason for correction:",
                                    placeholder="Why is this correction needed?",
                                    key=f"mobile_constraint_explain_{error['unique_id']}_{error['variable']}",
                                    height=80
                                )
                                st.markdown("---")
                        
                        # Process logic errors
                        if len(farmer_logic_errors) > 0:
                            for index, discrepancy in farmer_logic_errors.iterrows():
                                st.subheader(f"📊 {discrepancy['variable']}")
                                
                                col1, col2 = st.columns([2, 1])
                                
                                with col1:
                                    st.write(f"**You reported:** {discrepancy['value']}")
                                    st.write(f"**System shows:** {discrepancy['Troster Value']}")
                                    st.write(f"**Difference:** {int(discrepancy['value']) - int(discrepancy['Troster Value'])}")
                                
                                with col2:
                                    farmer_value = int(discrepancy['value'])
                                    troster_value = int(discrepancy['Troster Value'])
                                    max_val = max(farmer_value, troster_value) * 2
                                    
                                    correct_value = st.number_input(
                                        "Correct value:",
                                        min_value=0,
                                        max_value=max_val,
                                        value=farmer_value,
                                        key=f"mobile_logic_{discrepancy['unique_id']}_{discrepancy['variable']}",
                                        label_visibility="collapsed"
                                    )
                                
                                explanation = st.text_area(
                                    "Reason for difference:",
                                    placeholder="Why different from system record?",
                                    key=f"mobile_logic_explain_{discrepancy['unique_id']}_{discrepancy['variable']}",
                                    height=80
                                )
                                st.markdown("---")
            
            # Simple save button at bottom
            st.markdown("---")
            st.header("💾 Save Your Work")
            
            if st.button("✅ Save All Corrections", type="primary", use_container_width=True):
                corrections = []
                
                # Collect constraint corrections
                for farmer_id in all_farmers_with_errors:
                    farmer_errors = enumerator_constraints[enumerator_constraints['unique_id'] == farmer_id]
                    for index, error in farmer_errors.iterrows():
                        correct_value = st.session_state.get(f"mobile_constraint_{error['unique_id']}_{error['variable']}")
                        explanation = st.session_state.get(f"mobile_constraint_explain_{error['unique_id']}_{error['variable']}")
                        
                        if correct_value is not None:
                            correction_record = {
                                'error_type': 'constraint',
                                'username': error['username'],
                                'supervisor': error['supervisor'],
                                'woreda': error['woreda'],
                                'kebele': error['kebele'],
                                'farmer_name': error['farmer_name'],
                                'phone_no': error['phone_no'],
                                'subdate': error['subdate'],
                                'unique_id': error['unique_id'],
                                'variable': error['variable'],
                                'original_value': error['value'],
                                'reference_value': error['constraint'],
                                'correct_value': correct_value,
                                'explanation': explanation if explanation else "",
                                'corrected_by': selected_enumerator,
                                'correction_date': datetime.now().strftime("%d-%b-%y"),
                                'correction_timestamp': datetime.now().isoformat()
                            }
                            corrections.append(correction_record)
                            # Mark as corrected
                            st.session_state.corrected_errors.add(f"constraint_{error['unique_id']}_{error['variable']}")
                
                # Collect logic corrections
                for farmer_id in all_farmers_with_errors:
                    farmer_discrepancies = enumerator_logic[enumerator_logic['unique_id'] == farmer_id]
                    for index, discrepancy in farmer_discrepancies.iterrows():
                        correct_value = st.session_state.get(f"mobile_logic_{discrepancy['unique_id']}_{discrepancy['variable']}")
                        explanation = st.session_state.get(f"mobile_logic_explain_{discrepancy['unique_id']}_{discrepancy['variable']}")
                        
                        if correct_value is not None:
                            correction_record = {
                                'error_type': 'logic',
                                'username': discrepancy['username'],
                                'supervisor': discrepancy['supervisor'],
                                'woreda': discrepancy['woreda'],
                                'kebele': discrepancy['kebele'],
                                'farmer_name': discrepancy['farmer_name'],
                                'phone_no': discrepancy['phone_no'],
                                'subdate': discrepancy['subdate'],
                                'unique_id': discrepancy['unique_id'],
                                'variable': discrepancy['variable'],
                                'original_value': discrepancy['value'],
                                'reference_value': discrepancy['Troster Value'],
                                'correct_value': correct_value,
                                'explanation': explanation if explanation else "",
                                'corrected_by': selected_enumerator,
                                'correction_date': datetime.now().strftime("%d-%b-%y"),
                                'correction_timestamp': datetime.now().isoformat()
                            }
                            corrections.append(correction_record)
                            # Mark as corrected
                            st.session_state.corrected_errors.add(f"logic_{discrepancy['unique_id']}_{discrepancy['variable']}")
                
                if corrections:
                    corrections_df = pd.DataFrame(corrections)
                    
                    # Save to GitHub
                    if save_corrections_to_github(corrections_df):
                        st.success(f"✅ Saved {len(corrections)} corrections to secure repository! Errors are now cleared.")
                        st.balloons()
                    else:
                        st.warning("⚠️ Failed to save to repository. Please try again.")
                        
                else:
                    st.warning("No corrections found to save.")

# Simple footer
st.markdown("---")
st.markdown("📱 *HFC Correction System*")