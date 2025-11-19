import streamlit as st
import pandas as pd
from datetime import datetime
import io
import re
import requests
import base64
from typing import Tuple, Optional, List, Dict

# ============================================================================
# CONFIGURATION
# ============================================================================

st.set_page_config(
    page_title="HFC Data Correction",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={
        'About': "HFC Data Correction System v2.0"
    }
)

# Constants
GITHUB_OWNER = "mohammed-seid"
GITHUB_REPO = "hfc-data-private"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"
CACHE_TTL = 3600  # 1 hour

# ============================================================================
# STYLING - Mobile-First Design
# ============================================================================

st.markdown("""
    <style>
    /* Mobile-optimized styles */
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        height: 50px;
        font-size: 16px;
        font-weight: 600;
    }
    
    .stExpander {
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        margin-bottom: 12px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    .farmer-card {
        background: #f8f9fa;
        padding: 12px;
        border-radius: 8px;
        margin-bottom: 8px;
        border-left: 4px solid #4CAF50;
    }
    
    .error-badge {
        background: #ff6b6b;
        color: white;
        padding: 4px 12px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 600;
    }
    
    .success-badge {
        background: #51cf66;
        color: white;
        padding: 4px 12px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 600;
    }
    
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 12px;
        color: white;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    
    /* Better mobile spacing */
    @media (max-width: 768px) {
        .stTextInput, .stNumberInput, .stTextArea {
            margin-bottom: 16px;
        }
        
        .stMetric {
            padding: 12px;
        }
    }
    
    /* Progress indicator */
    .progress-bar {
        height: 8px;
        background: #e0e0e0;
        border-radius: 4px;
        overflow: hidden;
        margin: 16px 0;
    }
    
    .progress-fill {
        height: 100%;
        background: linear-gradient(90deg, #4CAF50, #8BC34A);
        transition: width 0.3s ease;
    }
    </style>
""", unsafe_allow_html=True)

# ============================================================================
# SESSION STATE INITIALIZATION
# ============================================================================

def initialize_session_state():
    """Initialize all session state variables"""
    defaults = {
        'corrected_errors': set(),
        'all_corrections_data': {},
        'is_admin': False,
        'selected_enumerator': None,
        'show_completed': False,
        'filter_error_type': 'All'
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

initialize_session_state()

# ============================================================================
# GITHUB API FUNCTIONS
# ============================================================================

def get_github_headers() -> Dict[str, str]:
    """Get GitHub API headers with authentication"""
    token = st.secrets.get("github", {}).get("token")
    if not token:
        raise ValueError("GitHub token not configured in secrets")
    
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

def fetch_file_from_github(filename: str) -> Optional[pd.DataFrame]:
    """Fetch and parse CSV file from GitHub"""
    try:
        headers = get_github_headers()
        url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{filename}"
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            st.error(f"Failed to load {filename}: {response.status_code}")
            return None
        
        content = base64.b64decode(response.json()['content']).decode('utf-8')
        return pd.read_csv(io.StringIO(content))
        
    except requests.exceptions.Timeout:
        st.error(f"⏱️ Timeout loading {filename}. Please check your connection.")
        return None
    except Exception as e:
        st.error(f"Error loading {filename}: {str(e)}")
        return None

@st.cache_data(ttl=CACHE_TTL)
def load_data_from_github() -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """Load constraints and logic data from GitHub with caching"""
    constraints_df = fetch_file_from_github("constraints.csv")
    logic_df = fetch_file_from_github("logic.csv")
    
    if constraints_df is not None and logic_df is not None:
        st.success("✅ Data loaded from secure repository")
    
    return constraints_df, logic_df

def load_existing_corrections() -> Optional[pd.DataFrame]:
    """Load existing corrections from GitHub"""
    try:
        headers = get_github_headers()
        corrections_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/corrections.csv"
        response = requests.get(corrections_url, headers=headers)
        
        if response.status_code == 200:
            corrections_content = base64.b64decode(response.json()['content']).decode('utf-8')
            return pd.read_csv(io.StringIO(corrections_content))
        else:
            return None
    except:
        return None

def save_corrections_to_github(corrections_df: pd.DataFrame) -> bool:
    """Save or append corrections to GitHub"""
    try:
        headers = get_github_headers()
        corrections_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/corrections.csv"
        
        # Check if file exists and load existing data
        response = requests.get(corrections_url, headers=headers)
        sha = None
        
        if response.status_code == 200:
            sha = response.json()['sha']
            # Load existing corrections
            existing_content = base64.b64decode(response.json()['content']).decode('utf-8')
            existing_df = pd.read_csv(io.StringIO(existing_content))
            # Append new corrections
            corrections_df = pd.concat([existing_df, corrections_df], ignore_index=True)
        
        # Convert to CSV and encode
        csv_data = corrections_df.to_csv(index=False)
        encoded_data = base64.b64encode(csv_data.encode()).decode()
        
        # Prepare payload
        payload = {
            "message": f"Add corrections - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "content": encoded_data,
            "branch": "main"
        }
        
        if sha:
            payload["sha"] = sha
            
        response = requests.put(corrections_url, headers=headers, json=payload, timeout=10)
        return response.status_code in [200, 201]
        
    except Exception as e:
        st.error(f"Error saving to GitHub: {str(e)}")
        return False

def check_token_validity() -> bool:
    """Verify GitHub token is valid"""
    try:
        headers = get_github_headers()
        response = requests.get("https://api.github.com/user", headers=headers, timeout=5)
        
        if response.status_code == 401:
            st.error("🔐 Access token expired. Please contact administrator.")
            return False
        return True
    except:
        return False

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_unique_id_column(df: pd.DataFrame) -> Optional[str]:
    """Find the unique ID column name in the dataframe"""
    if df is None or len(df) == 0:
        return None
    
    # Common variations of unique_id column
    possible_names = [
        'unique_id', 'Unique_id', 'UNIQUE_ID', 'UniqueID', 'unique_ID',
        'id', 'ID', 'farmer_id', 'Farmer_ID', 'farmerid'
    ]
    
    for col_name in possible_names:
        if col_name in df.columns:
            return col_name
    
    # If not found, return the first column that might be an ID
    for col in df.columns:
        if 'id' in col.lower():
            return col
    
    return None

def safe_get_unique_ids(df: pd.DataFrame) -> set:
    """Safely get unique IDs from dataframe"""
    if df is None or len(df) == 0:
        return set()
    
    id_col = get_unique_id_column(df)
    if id_col is None:
        return set()
    
    return set(df[id_col].unique())

# ============================================================================
# DATA PROCESSING FUNCTIONS
# ============================================================================

def extract_constraint_limits(constraint_text: str) -> Tuple[int, int]:
    """Extract min/max values from constraint text for display purposes only"""
    min_val, max_val = 0, 100000
    
    try:
        constraint_lower = str(constraint_text).lower()
        numbers = re.findall(r'\d+', constraint_text)
        
        if 'max' in constraint_lower and numbers:
            max_val = int(numbers[-1])
        if 'min' in constraint_lower and numbers:
            min_val = int(numbers[-1])
            
        # Handle range patterns like "between X and Y"
        if 'between' in constraint_lower and len(numbers) >= 2:
            min_val = int(numbers[0])
            max_val = int(numbers[1])
            
    except:
        pass
    
    return min_val, max_val

def get_corrected_error_keys(enumerator: str) -> set:
    """Get set of already corrected error keys for this enumerator"""
    existing_corrections = load_existing_corrections()
    
    if existing_corrections is None or len(existing_corrections) == 0:
        return set()
    
    # Filter corrections for this enumerator
    enumerator_corrections = existing_corrections[
        existing_corrections['corrected_by'] == enumerator
    ]
    
    # Create error keys
    corrected_keys = set()
    for _, row in enumerator_corrections.iterrows():
        # Try to get unique_id, handle if column name is different
        unique_id = None
        if 'unique_id' in row:
            unique_id = row['unique_id']
        else:
            # Try other possible column names
            for col in row.index:
                if 'id' in col.lower() and col != 'error_type':
                    unique_id = row[col]
                    break
        
        if unique_id:
            error_key = f"{row['error_type']}_{unique_id}_{row['variable']}"
            corrected_keys.add(error_key)
    
    return corrected_keys

def filter_uncorrected_errors(df: pd.DataFrame, error_type: str, enumerator: str) -> pd.DataFrame:
    """Remove already corrected errors from dataframe"""
    if df is None or len(df) == 0:
        return pd.DataFrame()
    
    # Get the unique ID column
    id_col = get_unique_id_column(df)
    if id_col is None:
        return pd.DataFrame()
    
    # Get corrected errors from GitHub
    corrected_keys = get_corrected_error_keys(enumerator)
    
    # Also check session state
    all_corrected = corrected_keys.union(st.session_state.corrected_errors)
    
    return df[~df.apply(
        lambda x: f"{error_type}_{x[id_col]}_{x['variable']}" in all_corrected,
        axis=1
    )]

def get_enumerator_statistics(constraints_df: pd.DataFrame, logic_df: pd.DataFrame) -> pd.DataFrame:
    """Get detailed statistics for each enumerator"""
    stats = []
    
    # Get all unique enumerators
    all_enumerators = set()
    if constraints_df is not None and len(constraints_df) > 0:
        all_enumerators.update(constraints_df['username'].unique())
    if logic_df is not None and len(logic_df) > 0:
        all_enumerators.update(logic_df['username'].unique())
    
    # Get all corrections
    existing_corrections = load_existing_corrections()
    
    for enumerator in sorted(all_enumerators):
        # Count total errors
        constraint_errors = 0
        logic_errors = 0
        
        if constraints_df is not None and len(constraints_df) > 0:
            constraint_errors = len(constraints_df[constraints_df['username'] == enumerator])
        
        if logic_df is not None and len(logic_df) > 0:
            logic_errors = len(logic_df[logic_df['username'] == enumerator])
        
        total_errors = constraint_errors + logic_errors
        
        # Count solved errors
        solved = 0
        if existing_corrections is not None:
            solved = len(existing_corrections[existing_corrections['corrected_by'] == enumerator])
        
        # Calculate remaining
        remaining = total_errors - solved
        
        # Calculate percentage
        percentage = (solved / total_errors * 100) if total_errors > 0 else 0
        
        stats.append({
            'Username': enumerator,
            'Total Errors': total_errors,
            'Solved': solved,
            'Remaining': remaining,
            'Progress (%)': round(percentage, 1)
        })
    
    stats_df = pd.DataFrame(stats)
    # Sort by remaining errors (descending)
    stats_df = stats_df.sort_values('Remaining', ascending=False)
    
    return stats_df

def get_comprehensive_error_analysis(constraints_df: pd.DataFrame, logic_df: pd.DataFrame) -> Dict:
    """Generate comprehensive error analysis summary"""
    analysis = {
        'error_type_overview': {},
        'error_rate_by_enumerator': [],
        'enumerators_without_errors': [],
        'most_common_variables': {},
        'strange_values': [],
        'overall_stats': {}
    }
    
    # Combine all errors
    all_errors = []
    
    if constraints_df is not None and len(constraints_df) > 0:
        constraint_errors = constraints_df.copy()
        constraint_errors['error_category'] = 'Constraint'
        all_errors.append(constraint_errors)
    
    if logic_df is not None and len(logic_df) > 0:
        logic_errors = logic_df.copy()
        logic_errors['error_category'] = 'Logic'
        all_errors.append(logic_errors)
    
    if not all_errors:
        return analysis
    
    combined_errors = pd.concat(all_errors, ignore_index=True)
    
    # Get all unique enumerators
    all_enumerators = set()
    if constraints_df is not None and len(constraints_df) > 0:
        all_enumerators.update(constraints_df['username'].unique())
    if logic_df is not None and len(logic_df) > 0:
        all_enumerators.update(logic_df['username'].unique())
    
    # 1. Error Type Overview
    id_col = get_unique_id_column(combined_errors)
    unique_farmers = combined_errors[id_col].nunique() if id_col else 0
    
    analysis['error_type_overview'] = {
        'Total Constraint Errors': len(constraints_df) if constraints_df is not None else 0,
        'Total Logic Errors': len(logic_df) if logic_df is not None else 0,
        'Total Errors': len(combined_errors),
        'Unique Farmers Affected': unique_farmers
    }
    
    # 2. Error Rate by Enumerator
    enumerator_analysis = []
    for enumerator in sorted(all_enumerators):
        enum_errors = combined_errors[combined_errors['username'] == enumerator]
        constraint_count = len(enum_errors[enum_errors['error_category'] == 'Constraint'])
        logic_count = len(enum_errors[enum_errors['error_category'] == 'Logic'])
        total_count = len(enum_errors)
        
        if total_count > 0:
            # Get corrections
            existing_corrections = load_existing_corrections()
            solved = 0
            if existing_corrections is not None:
                solved = len(existing_corrections[existing_corrections['corrected_by'] == enumerator])
            
            error_rate = (total_count / analysis['error_type_overview']['Total Errors'] * 100) if analysis['error_type_overview']['Total Errors'] > 0 else 0
            
            enumerator_analysis.append({
                'Username': enumerator,
                'Constraint Errors': constraint_count,
                'Logic Errors': logic_count,
                'Total Errors': total_count,
                'Solved': solved,
                'Remaining': total_count - solved,
                'Error Rate (%)': round(error_rate, 2),
                'Completion Rate (%)': round((solved / total_count * 100), 2) if total_count > 0 else 0
            })
    
    analysis['error_rate_by_enumerator'] = pd.DataFrame(enumerator_analysis).sort_values('Total Errors', ascending=False)
    
    # 3. Enumerators Without Errors
    enumerators_with_errors = set(combined_errors['username'].unique())
    analysis['enumerators_without_errors'] = [e for e in all_enumerators if e not in enumerators_with_errors]
    
    # 4. Most Common Variable Errors
    variable_counts = combined_errors.groupby(['variable', 'error_category']).size().reset_index(name='count')
    variable_counts = variable_counts.sort_values('count', ascending=False)
    
    analysis['most_common_variables'] = {
        'top_constraint_variables': variable_counts[variable_counts['error_category'] == 'Constraint'].head(10),
        'top_logic_variables': variable_counts[variable_counts['error_category'] == 'Logic'].head(10),
        'overall_top_variables': variable_counts.head(15)
    }
    
    # 5. Strange/Outlier Values Detection
    strange_values = []
    
    # Analyze constraint errors for extreme values
    if constraints_df is not None and len(constraints_df) > 0:
        for _, row in constraints_df.iterrows():
            try:
                value = float(row['value'])
                
                # Check for suspiciously large values
                if value > 100000:
                    strange_values.append({
                        'Type': 'Constraint - Extremely Large',
                        'Variable': row['variable'],
                        'Value': value,
                        'Username': row.get('username', 'N/A'),
                        'Farmer': row.get('farmer_name', 'N/A'),
                        'Constraint': row.get('constraint', 'N/A')
                    })
                
                # Check for negative values where they shouldn't be
                if value < 0 and 'temp' not in row['variable'].lower():
                    strange_values.append({
                        'Type': 'Constraint - Negative Value',
                        'Variable': row['variable'],
                        'Value': value,
                        'Username': row.get('username', 'N/A'),
                        'Farmer': row.get('farmer_name', 'N/A'),
                        'Constraint': row.get('constraint', 'N/A')
                    })
            except:
                # Non-numeric value
                strange_values.append({
                    'Type': 'Constraint - Non-Numeric',
                    'Variable': row['variable'],
                    'Value': row['value'],
                    'Username': row.get('username', 'N/A'),
                    'Farmer': row.get('farmer_name', 'N/A'),
                    'Constraint': row.get('constraint', 'N/A')
                })
    
    # Analyze logic errors for large discrepancies
    if logic_df is not None and len(logic_df) > 0:
        for _, row in logic_df.iterrows():
            try:
                farmer_val = float(row['value'])
                troster_val = float(row['Troster Value'])
                difference = abs(farmer_val - troster_val)
                
                # Large absolute discrepancy
                if difference > 1000:
                    strange_values.append({
                        'Type': 'Logic - Large Discrepancy',
                        'Variable': row['variable'],
                        'Value': f"Farmer: {farmer_val}, System: {troster_val}, Diff: {difference}",
                        'Username': row.get('username', 'N/A'),
                        'Farmer': row.get('farmer_name', 'N/A'),
                        'Constraint': f"Difference: {difference}"
                    })
                
                # Large percentage discrepancy (if both values are non-zero)
                if farmer_val > 0 and troster_val > 0:
                    percent_diff = abs((farmer_val - troster_val) / troster_val * 100)
                    if percent_diff > 200:  # More than 200% difference
                        strange_values.append({
                            'Type': 'Logic - Large % Difference',
                            'Variable': row['variable'],
                            'Value': f"Farmer: {farmer_val}, System: {troster_val}, {percent_diff:.1f}% diff",
                            'Username': row.get('username', 'N/A'),
                            'Farmer': row.get('farmer_name', 'N/A'),
                            'Constraint': f"{percent_diff:.1f}% difference"
                        })
            except:
                pass
    
    analysis['strange_values'] = pd.DataFrame(strange_values) if strange_values else pd.DataFrame()
    
    # 6. Overall Statistics
    enumerators_with_errors_count = len(enumerators_with_errors)
    analysis['overall_stats'] = {
        'Total Enumerators': len(all_enumerators),
        'Enumerators with Errors': enumerators_with_errors_count,
        'Enumerators without Errors': len(analysis['enumerators_without_errors']),
        'Average Errors per Enumerator': round(analysis['error_type_overview']['Total Errors'] / enumerators_with_errors_count, 2) if enumerators_with_errors_count > 0 else 0,
        'Unique Variables with Errors': combined_errors['variable'].nunique(),
        'Strange Values Detected': len(strange_values)
    }
    
    return analysis

# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================

def validate_corrections() -> Tuple[bool, List[str], int, int]:
    """Validate all corrections are complete with explanations"""
    total_errors = len(st.session_state.all_corrections_data)
    completed = 0
    missing = []
    
    for error_key, correction_data in st.session_state.all_corrections_data.items():
        explanation = correction_data.get('explanation', '').strip()
        
        # Check if explanation exists
        if not explanation:
            var_name = correction_data['error_data']['variable']
            error_type = "Constraint" if correction_data['error_type'] == 'constraint' else "Logic"
            missing.append(f"{error_type}: {var_name} - No explanation provided")
            continue
        
        # For constraint errors outside range, require detailed explanation
        if correction_data['error_type'] == 'constraint':
            if correction_data.get('outside_range', False):
                if len(explanation) < 20:
                    var_name = correction_data['error_data']['variable']
                    missing.append(f"Constraint: {var_name} - Out-of-range value needs detailed explanation (min 20 chars)")
                    continue
        
        # For logic errors that differ from both values, encourage detailed explanation
        if correction_data['error_type'] == 'logic':
            if correction_data.get('differs_from_both', False):
                if len(explanation) < 15:
                    var_name = correction_data['error_data']['variable']
                    missing.append(f"Logic: {var_name} - Value differs from both records, needs better explanation")
                    continue
        
        completed += 1
    
    return completed == total_errors, missing, completed, total_errors

def validate_farmer_corrections(farmer_id: str, id_col: str) -> Tuple[bool, List[str], int, int]:
    """Validate corrections for a specific farmer"""
    farmer_corrections = {}
    
    for k, v in st.session_state.all_corrections_data.items():
        farmer_id_val = v['error_data'].get(id_col)
        if str(farmer_id_val) == str(farmer_id):
            farmer_corrections[k] = v
    
    total_errors = len(farmer_corrections)
    completed = 0
    missing = []
    
    for error_key, correction_data in farmer_corrections.items():
        explanation = correction_data.get('explanation', '').strip()
        
        # Check if explanation exists
        if not explanation:
            var_name = correction_data['error_data']['variable']
            error_type = "Constraint" if correction_data['error_type'] == 'constraint' else "Logic"
            missing.append(f"{error_type}: {var_name}")
            continue
        
        # For constraint errors outside range, require detailed explanation
        if correction_data['error_type'] == 'constraint':
            if correction_data.get('outside_range', False):
                if len(explanation) < 20:
                    var_name = correction_data['error_data']['variable']
                    missing.append(f"Constraint: {var_name} - Needs detailed explanation")
                    continue
        
        # For logic errors that differ from both values
        if correction_data['error_type'] == 'logic':
            if correction_data.get('differs_from_both', False):
                if len(explanation) < 15:
                    var_name = correction_data['error_data']['variable']
                    missing.append(f"Logic: {var_name} - Needs better explanation")
                    continue
        
        completed += 1
    
    return completed == total_errors, missing, completed, total_errors

# ============================================================================
# UI COMPONENTS
# ============================================================================

def render_progress_bar(current: int, total: int):
    """Render a visual progress bar"""
    percentage = (current / total * 100) if total > 0 else 0
    
    st.markdown(f"""
        <div class="progress-bar">
            <div class="progress-fill" style="width: {percentage}%"></div>
        </div>
        <p style="text-align: center; color: #666;">
            {current} of {total} completed ({percentage:.0f}%)
        </p>
    """, unsafe_allow_html=True)

def render_metric_card(label: str, value: str, icon: str = "📊"):
    """Render an attractive metric card"""
    st.markdown(f"""
        <div class="metric-card">
            <div style="font-size: 32px; margin-bottom: 8px;">{icon}</div>
            <div style="font-size: 28px; font-weight: 700;">{value}</div>
            <div style="font-size: 14px; opacity: 0.9;">{label}</div>
        </div>
    """, unsafe_allow_html=True)

def render_farmer_header(farmer_name: str, phone_no: str, error_count: int, completed_count: int = 0):
    """Render farmer information header"""
    if completed_count > 0:
        badge = f'<span class="success-badge">{completed_count} ready</span> <span class="error-badge">{error_count - completed_count} pending</span>'
    else:
        badge = f'<span class="error-badge">{error_count} issues</span>'
    
    st.markdown(f"""
        <div class="farmer-card">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <div style="font-size: 18px; font-weight: 600;">👨‍🌾 {farmer_name}</div>
                    <div style="font-size: 14px; color: #666; margin-top: 4px;">
                        📞 <a href="tel:{phone_no}" style="color: #667eea; text-decoration: none;">{phone_no}</a>
                    </div>
                </div>
                <div>{badge}</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

def render_constraint_error(error: pd.Series, error_key: str, id_col: str):
    """Render constraint error correction form"""
    st.markdown(f"### 🔒 {error['variable']}")
    
    # Extract constraints for display purposes only
    min_val, max_val = extract_constraint_limits(error['constraint'])
    
    # Use original value as default, but don't restrict input
    try:
        default_value = int(error['value'])
    except:
        default_value = 0
    
    # Two-column layout for mobile
    col1, col2 = st.columns([3, 2])
    
    with col1:
        st.info(f"**Current Value:** {error['value']}")
        st.caption(f"**Rule:** {error['constraint']}")
        st.caption(f"💡 Expected range: {min_val} - {max_val}")
    
    with col2:
        # NO RESTRICTIONS on corrected value - enumerator can input any value
        correct_value = st.number_input(
            "Corrected Value",
            value=default_value,
            step=1,
            key=f"value_{error_key}",
            help="Enter the actual correct value (no restrictions)"
        )
    
    # Show warning if value is outside expected range
    if correct_value < min_val or correct_value > max_val:
        st.warning(f"⚠️ Value is outside expected range ({min_val}-{max_val}). Please explain why in detail below.")
    
    explanation = st.text_area(
        "📝 Explanation (Required)",
        placeholder="Why is this correction needed? What did the farmer say? If outside expected range, provide detailed justification.",
        key=f"explain_{error_key}",
        height=120,
        help="Please provide a clear explanation for the correction, especially if the value is outside the expected range"
    )
    
    # Store correction data
    st.session_state.all_corrections_data[error_key] = {
        'error_type': 'constraint',
        'error_data': error,
        'correct_value': correct_value,
        'explanation': explanation,
        'outside_range': correct_value < min_val or correct_value > max_val,
        'id_column': id_col
    }
    
    # Visual validation feedback
    if explanation and explanation.strip():
        # Check if explanation is substantial for out-of-range values
        if correct_value < min_val or correct_value > max_val:
            if len(explanation.strip()) < 20:
                st.warning("⚠️ Out-of-range value requires detailed explanation (at least 20 characters)")
            else:
                st.success("✅ Explanation provided")
        else:
            st.success("✅ Explanation provided")
    else:
        st.error("❌ Explanation required before saving")

def render_logic_error(discrepancy: pd.Series, error_key: str, id_col: str):
    """Render logic error correction form"""
    st.markdown(f"### 📊 {discrepancy['variable']}")
    
    try:
        farmer_value = int(discrepancy['value'])
        troster_value = int(discrepancy['Troster Value'])
    except:
        farmer_value = 0
        troster_value = 0
    
    difference = farmer_value - troster_value
    
    # Show comparison
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Your Report", farmer_value)
    with col2:
        st.metric("System Record", troster_value)
    with col3:
        st.metric("Difference", difference, delta=difference)
    
    # Correction input - NO RESTRICTIONS
    correct_value = st.number_input(
        "Corrected Value",
        value=farmer_value,
        step=1,
        key=f"value_{error_key}",
        help="Enter the actual correct value after verification (no restrictions)"
    )
    
    # Show info about the discrepancy
    if correct_value != farmer_value and correct_value != troster_value:
        st.info(f"💡 Corrected value differs from both reported ({farmer_value}) and system ({troster_value}) values")
    
    explanation = st.text_area(
        "📝 Explanation (Required)",
        placeholder="Why is there a difference? What did you verify with the farmer? Explain the correct value.",
        key=f"explain_{error_key}",
        height=120
    )
    
    # Store correction data
    st.session_state.all_corrections_data[error_key] = {
        'error_type': 'logic',
        'error_data': discrepancy,
        'correct_value': correct_value,
        'explanation': explanation,
        'differs_from_both': correct_value != farmer_value and correct_value != troster_value,
        'id_column': id_col
    }
    
    # Visual validation feedback
    if explanation and explanation.strip():
        st.success("✅ Explanation provided")
    else:
        st.error("❌ Explanation required before saving")

# ============================================================================
# SAVE FUNCTIONS
# ============================================================================

def save_farmer_corrections(farmer_id: str, selected_enumerator: str, id_col: str) -> bool:
    """Save corrections for a specific farmer"""
    # Get corrections for this farmer
    farmer_corrections = {}
    for k, v in st.session_state.all_corrections_data.items():
        if str(v['error_data'].get(id_col)) == str(farmer_id):
            farmer_corrections[k] = v
    
    if not farmer_corrections:
        return False
    
    # Prepare corrections
    corrections = []
    
    for error_key, correction_data in farmer_corrections.items():
        error_data = correction_data['error_data']
        
        base_record = {
            'error_type': correction_data['error_type'],
            'username': error_data.get('username', ''),
            'supervisor': error_data.get('supervisor', ''),
            'woreda': error_data.get('woreda', ''),
            'kebele': error_data.get('kebele', ''),
            'farmer_name': error_data.get('farmer_name', ''),
            'phone_no': error_data.get('phone_no', ''),
            'subdate': error_data.get('subdate', ''),
            'unique_id': error_data.get(id_col, ''),
            'variable': error_data.get('variable', ''),
            'original_value': error_data.get('value', ''),
            'correct_value': correction_data['correct_value'],
            'explanation': correction_data['explanation'],
            'corrected_by': selected_enumerator,
            'correction_date': datetime.now().strftime("%d-%b-%y"),
            'correction_timestamp': datetime.now().isoformat(),
            'outside_range': correction_data.get('outside_range', False),
            'differs_from_both': correction_data.get('differs_from_both', False)
        }
        
        if correction_data['error_type'] == 'constraint':
            base_record['reference_value'] = error_data.get('constraint', '')
        else:
            base_record['reference_value'] = error_data.get('Troster Value', '')
        
        corrections.append(base_record)
    
    if corrections:
        corrections_df = pd.DataFrame(corrections)
        
        if save_corrections_to_github(corrections_df):
            # Mark as corrected in session state
            for error_key in farmer_corrections.keys():
                st.session_state.corrected_errors.add(error_key)
                # Remove from pending corrections
                if error_key in st.session_state.all_corrections_data:
                    del st.session_state.all_corrections_data[error_key]
            return True
    
    return False

# ============================================================================
# ADMIN DASHBOARD
# ============================================================================

def render_admin_dashboard(constraints_df: pd.DataFrame, logic_df: pd.DataFrame):
    """Render admin dashboard with enhanced analytics"""
    st.title("📊 Admin Dashboard - HFC Data Correction")
    
    # Logout button
    if st.button("🚪 Logout", type="secondary"):
        st.session_state.is_admin = False
        st.rerun()
    
    st.markdown("---")
    
    # ========== COMPREHENSIVE SUMMARY SECTION ==========
    st.header("📈 High Frequency Check Summary")
    
    with st.spinner("Generating comprehensive analysis..."):
        analysis = get_comprehensive_error_analysis(constraints_df, logic_df)
    
    # Overall Error Type Overview
    st.subheader("🎯 Error Type Overview")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        render_metric_card(
            "Total Errors", 
            str(analysis['error_type_overview']['Total Errors']), 
            "⚠️"
        )
    with col2:
        render_metric_card(
            "Constraint Errors", 
            str(analysis['error_type_overview']['Total Constraint Errors']), 
            "🔒"
        )
    with col3:
        render_metric_card(
            "Logic Errors", 
            str(analysis['error_type_overview']['Total Logic Errors']), 
            "📊"
        )
    with col4:
        render_metric_card(
            "Farmers Affected", 
            str(analysis['error_type_overview']['Unique Farmers Affected']), 
            "👨‍🌾"
        )
    
    st.markdown("---")
    
    # Error Rate by Enumerator
    st.subheader("👥 Error Rate by Enumerator")
    
    if not analysis['error_rate_by_enumerator'].empty:
        # Display as interactive table
        st.dataframe(
            analysis['error_rate_by_enumerator'],
            use_container_width=True,
            height=400
        )
        
        # Visualization
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Error Distribution**")
            fig_data = analysis['error_rate_by_enumerator'].nlargest(10, 'Total Errors')
            if len(fig_data) > 0:
                st.bar_chart(fig_data.set_index('Username')[['Constraint Errors', 'Logic Errors']])
        
        with col2:
            st.markdown("**Completion Rate**")
            if len(analysis['error_rate_by_enumerator']) > 0:
                st.bar_chart(analysis['error_rate_by_enumerator'].set_index('Username')['Completion Rate (%)'])
    
    st.markdown("---")
    
    # Enumerators Without Errors
    st.subheader("✅ Enumerators Without Errors")
    
    if analysis['enumerators_without_errors']:
        st.success(f"**{len(analysis['enumerators_without_errors'])} enumerators** have no errors:")
        cols = st.columns(4)
        for idx, enum in enumerate(analysis['enumerators_without_errors']):
            with cols[idx % 4]:
                st.write(f"✅ {enum}")
    else:
        st.info("All enumerators have at least one error to correct")
    
    st.markdown("---")
    
    # Most Common Variable Errors
    st.subheader("🔍 Most Frequent Variable Errors")
    
    tab1, tab2, tab3 = st.tabs(["📊 Overall", "🔒 Constraints", "📈 Logic"])
    
    with tab1:
        if not analysis['most_common_variables']['overall_top_variables'].empty:
            st.markdown("**Top 15 Variables with Most Errors**")
            top_vars = analysis['most_common_variables']['overall_top_variables']
            st.dataframe(
                top_vars.rename(columns={'count': 'Error Count', 'error_category': 'Type'}),
                use_container_width=True
            )
            if len(top_vars) > 0:
                st.bar_chart(top_vars.head(10).set_index('variable')['count'])
    
    with tab2:
        if not analysis['most_common_variables']['top_constraint_variables'].empty:
            st.markdown("**Top 10 Constraint Variables**")
            st.dataframe(
                analysis['most_common_variables']['top_constraint_variables'].rename(columns={'count': 'Error Count'}),
                use_container_width=True
            )
    
    with tab3:
        if not analysis['most_common_variables']['top_logic_variables'].empty:
            st.markdown("**Top 10 Logic Variables**")
            st.dataframe(
                analysis['most_common_variables']['top_logic_variables'].rename(columns={'count': 'Error Count'}),
                use_container_width=True
            )
    
    st.markdown("---")
    
    # Strange/Outlier Values
    st.subheader("🚨 Strange & Outlier Values Detected")
    
    if not analysis['strange_values'].empty:
        st.warning(f"**{len(analysis['strange_values'])} suspicious values** detected that need attention:")
        
        # Filter options
        strange_type_filter = st.multiselect(
            "Filter by type:",
            options=analysis['strange_values']['Type'].unique(),
            default=list(analysis['strange_values']['Type'].unique())
        )
        
        filtered_strange = analysis['strange_values'][
            analysis['strange_values']['Type'].isin(strange_type_filter)
        ]
        
        st.dataframe(
            filtered_strange,
            use_container_width=True,
            height=300
        )
        
        # Download strange values
        csv_strange = filtered_strange.to_csv(index=False)
        st.download_button(
            label="📥 Download Strange Values Report",
            data=csv_strange,
            file_name=f"strange_values_{datetime.now().strftime('%Y%m%d')}.csv",
            mime='text/csv'
        )
    else:
        st.success("✅ No suspicious outlier values detected")
    
    st.markdown("---")
    
    # Overall Statistics Summary
    st.subheader("📊 Overall Statistics")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Enumerators with Errors",
            analysis['overall_stats']['Enumerators with Errors'],
            delta=f"{analysis['overall_stats']['Enumerators without Errors']} clean"
        )
    
    with col2:
        st.metric(
            "Avg Errors/Enumerator",
            analysis['overall_stats']['Average Errors per Enumerator']
        )
    
    with col3:
        st.metric(
            "Unique Variables",
            analysis['overall_stats']['Unique Variables with Errors']
        )
    
    with col4:
        st.metric(
            "Strange Values",
            analysis['overall_stats']['Strange Values Detected'],
            delta="Need review" if analysis['overall_stats']['Strange Values Detected'] > 0 else "All good",
            delta_color="inverse"
        )
    
    st.markdown("---")
    st.markdown("---")
    
    # ========== PROGRESS TRACKING ==========
    
    # Get statistics
    stats_df = get_enumerator_statistics(constraints_df, logic_df)
    
    # Overall metrics
    total_errors = stats_df['Total Errors'].sum()
    total_solved = stats_df['Solved'].sum()
    
    # Overall progress
    st.subheader("📈 Overall Progress")
    render_progress_bar(total_solved, total_errors)
    
    st.markdown("---")
    
    # Enumerator-wise statistics
    st.subheader("👥 Enumerator Progress Details")
    
    # Display enumerator cards
    for idx, row in stats_df.iterrows():
        if row['Total Errors'] > 0:
            with st.expander(f"👤 {row['Username']} - {row['Remaining']} remaining ({row['Progress (%)']}% complete)", expanded=False):
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Total Errors", row['Total Errors'])
                with col2:
                    st.metric("Solved", row['Solved'], delta=row['Solved'])
                with col3:
                    st.metric("Remaining", row['Remaining'], delta=-row['Remaining'], delta_color="inverse")
                with col4:
                    st.metric("Progress", f"{row['Progress (%)']}%")
                
                # Progress bar for this enumerator
                render_progress_bar(row['Solved'], row['Total Errors'])
    
    st.markdown("---")
    
    # Detailed corrections view
    st.subheader("📋 All Corrections")
    
    try:
        headers = get_github_headers()
        corrections_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/corrections.csv"
        response = requests.get(corrections_url, headers=headers)
        
        if response.status_code == 200:
            corrections_content = base64.b64decode(response.json()['content']).decode('utf-8')
            all_corrections = pd.read_csv(io.StringIO(corrections_content))
            
            # Filters
            filter_col1, filter_col2, filter_col3 = st.columns(3)
            
            with filter_col1:
                selected_enumerator = st.multiselect(
                    "Filter by Enumerator",
                    options=sorted(all_corrections['corrected_by'].unique()),
                    default=[]
                )
            
            with filter_col2:
                selected_error_type = st.multiselect(
                    "Filter by Error Type",
                    options=['constraint', 'logic'],
                    default=[]
                )
            
            with filter_col3:
                show_flagged = st.checkbox("Show flagged corrections only", value=False)
            
            # Apply filters
            filtered_df = all_corrections.copy()
            if selected_enumerator:
                filtered_df = filtered_df[filtered_df['corrected_by'].isin(selected_enumerator)]
            if selected_error_type:
                filtered_df = filtered_df[filtered_df['error_type'].isin(selected_error_type)]
            if 'outside_range' in filtered_df.columns and show_flagged:
                filtered_df = filtered_df[filtered_df['outside_range'] == True]
            
            # Display data
            st.markdown(f"**Showing {len(filtered_df)} of {len(all_corrections)} corrections**")
            
            st.dataframe(
                filtered_df.sort_values('correction_timestamp', ascending=False),
                use_container_width=True,
                height=400
            )
            
            # Statistics about flagged items
            if 'outside_range' in all_corrections.columns:
                out_of_range_count = all_corrections['outside_range'].sum()
                if out_of_range_count > 0:
                    st.warning(f"⚠️ {out_of_range_count} corrections have values outside expected constraints")
            
            # Download options
            st.markdown("---")
            st.subheader("💾 Download Data")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                csv = filtered_df.to_csv(index=False)
                st.download_button(
                    label="📥 Download Filtered Data",
                    data=csv,
                    file_name=f"corrections_filtered_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime='text/csv',
                    use_container_width=True
                )
            
            with col2:
                csv_all = all_corrections.to_csv(index=False)
                st.download_button(
                    label="📥 Download All Corrections",
                    data=csv_all,
                    file_name=f"corrections_all_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime='text/csv',
                    use_container_width=True
                )
            
            with col3:
                stats_csv = stats_df.to_csv(index=False)
                st.download_button(
                    label="📥 Download Statistics",
                    data=stats_csv,
                    file_name=f"enumerator_stats_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime='text/csv',
                    use_container_width=True
                )
            
        else:
            st.info("📭 No corrections submitted yet.")
            
    except Exception as e:
        st.error(f"Error loading corrections data: {str(e)}")

# ============================================================================
# ENUMERATOR INTERFACE
# ============================================================================

def render_enumerator_interface(constraints_df: pd.DataFrame, logic_df: pd.DataFrame):
    """Render main enumerator correction interface"""
    
    st.title("🌱 HFC Data Correction")
    st.markdown("### Correct data errors for farmers")
    
    # Enumerator selection
    st.markdown("---")
    st.subheader("👤 Select Your Account")
    
    # Get all unique enumerators
    all_enumerators = set()
    if constraints_df is not None and len(constraints_df) > 0:
        all_enumerators.update(constraints_df['username'].unique())
    if logic_df is not None and len(logic_df) > 0:
        all_enumerators.update(logic_df['username'].unique())
    
    all_enumerators = sorted(list(all_enumerators))
    
    if not all_enumerators:
        st.error("No enumerators found in the data")
        return
    
    selected_enumerator = st.selectbox(
        "Your username:",
        options=all_enumerators,
        index=0 if not st.session_state.selected_enumerator else (all_enumerators.index(st.session_state.selected_enumerator) if st.session_state.selected_enumerator in all_enumerators else 0),
        key="enumerator_select"
    )
    
    st.session_state.selected_enumerator = selected_enumerator
    
    # Get ID columns
    constraint_id_col = get_unique_id_column(constraints_df)
    logic_id_col = get_unique_id_column(logic_df)
    
    if constraint_id_col is None and logic_id_col is None:
        st.error("❌ Cannot find unique ID column in data. Please check your CSV files.")
        st.info("Available columns in constraints: " + str(list(constraints_df.columns) if constraints_df is not None else "N/A"))
        st.info("Available columns in logic: " + str(list(logic_df.columns) if logic_df is not None else "N/A"))
        return
    
    # Use the first valid ID column found
    id_col = constraint_id_col if constraint_id_col else logic_id_col
    
    # Filter data - now checks both session state and GitHub
    enumerator_constraints = filter_uncorrected_errors(
        constraints_df[constraints_df['username'] == selected_enumerator] if constraints_df is not None else pd.DataFrame(),
        'constraint',
        selected_enumerator
    )
    
    enumerator_logic = filter_uncorrected_errors(
        logic_df[logic_df['username'] == selected_enumerator] if logic_df is not None else pd.DataFrame(),
        'logic',
        selected_enumerator
    )
    
    # Get unique farmers with errors
    all_farmers_with_errors = sorted(
        safe_get_unique_ids(enumerator_constraints) | 
        safe_get_unique_ids(enumerator_logic)
    )
    
    st.markdown("---")
    
    # Summary metrics
    if len(all_farmers_with_errors) == 0:
        st.success("🎉 All errors corrected! No pending issues.")
        st.balloons()
        return
    
    total_errors = len(enumerator_constraints) + len(enumerator_logic)
    
    # Count already saved corrections
    existing_corrections = load_existing_corrections()
    saved_count = 0
    if existing_corrections is not None:
        saved_count = len(existing_corrections[existing_corrections['corrected_by'] == selected_enumerator])
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        render_metric_card("Farmers Pending", str(len(all_farmers_with_errors)), "👨‍🌾")
    with col2:
        render_metric_card("Issues Remaining", str(total_errors), "⚠️")
    with col3:
        render_metric_card("Already Saved", str(saved_count), "✅")
    
    st.markdown("---")
    
    # Error type filter
    error_filter = st.radio(
        "Filter by error type:",
        options=["All", "Constraints Only", "Logic Only"],
        horizontal=True
    )
    
    st.markdown("---")
    
    # Process each farmer
    st.subheader("📞 Call Farmers & Correct Errors")
    st.caption("Complete corrections for each farmer and save individually, or save all at once")
    
    for farmer_id in all_farmers_with_errors:
        farmer_constraint_errors = enumerator_constraints[
            enumerator_constraints[id_col] == farmer_id
        ] if len(enumerator_constraints) > 0 else pd.DataFrame()
        
        farmer_logic_errors = enumerator_logic[
            enumerator_logic[id_col] == farmer_id
        ] if len(enumerator_logic) > 0 else pd.DataFrame()
        
        # Apply filter
        if error_filter == "Constraints Only" and len(farmer_constraint_errors) == 0:
            continue
        if error_filter == "Logic Only" and len(farmer_logic_errors) == 0:
            continue
        
        total_farmer_errors = len(farmer_constraint_errors) + len(farmer_logic_errors)
        
        if total_farmer_errors > 0:
            # Get farmer info
            farmer_name = ""
            phone_no = ""
            
            if len(farmer_constraint_errors) > 0:
                farmer_name = farmer_constraint_errors.iloc[0].get('farmer_name', 'Unknown')
                phone_no = farmer_constraint_errors.iloc[0].get('phone_no', 'N/A')
            elif len(farmer_logic_errors) > 0:
                farmer_name = farmer_logic_errors.iloc[0].get('farmer_name', 'Unknown')
                phone_no = farmer_logic_errors.iloc[0].get('phone_no', 'N/A')
            
            # Check how many corrections are ready for this farmer
            is_farmer_valid, farmer_missing, farmer_completed, farmer_total = validate_farmer_corrections(farmer_id, id_col)
            
            # Render farmer section
            with st.expander(f"👨‍🌾 {farmer_name} 📞 {phone_no}", expanded=False):
                render_farmer_header(farmer_name, phone_no, total_farmer_errors, farmer_completed)
                
                st.markdown("---")
                
                # Process constraint errors
                if len(farmer_constraint_errors) > 0:
                    st.markdown("#### 🔒 Constraint Errors")
                    for idx, error in farmer_constraint_errors.iterrows():
                        error_key = f"constraint_{error[id_col]}_{error['variable']}"
                        render_constraint_error(error, error_key, id_col)
                        st.markdown("---")
                
                # Process logic errors
                if len(farmer_logic_errors) > 0:
                    st.markdown("#### 📊 Logic Discrepancies")
                    for idx, discrepancy in farmer_logic_errors.iterrows():
                        error_key = f"logic_{discrepancy[id_col]}_{discrepancy['variable']}"
                        render_logic_error(discrepancy, error_key, id_col)
                        st.markdown("---")
                
                # Individual farmer save button
                st.markdown("---")
                
                if is_farmer_valid:
                    if st.button(f"💾 Save Corrections for {farmer_name}", key=f"save_{farmer_id}", type="primary", use_container_width=True):
                        with st.spinner("Saving..."):
                            if save_farmer_corrections(farmer_id, selected_enumerator, id_col):
                                st.success(f"✅ Saved {farmer_completed} corrections for {farmer_name}!")
                                st.balloons()
                                # Clear cache to reload data
                                load_data_from_github.clear()
                                st.rerun()
                            else:
                                st.error("Failed to save. Please try again.")
                else:
                    st.warning(f"⚠️ Complete all corrections for this farmer to save ({farmer_completed}/{farmer_total} ready)")
                    with st.expander("Missing items"):
                        for item in farmer_missing:
                            st.write(f"• {item}")
    
    # Save all section
    st.markdown("---")
    st.header("💾 Save All Remaining Corrections")
    
    # Show overall progress
    is_valid, missing_list, completed, total = validate_corrections()
    render_progress_bar(completed, total)
    
    if not is_valid:
        st.warning(f"⚠️ Some corrections are incomplete ({len(missing_list)} items)")
        with st.expander("See incomplete items"):
            for item in missing_list:
                st.write(f"• {item}")
    
    # Save all button
    save_button_type = "primary" if is_valid else "secondary"
    
    if st.button("✅ Save All Completed Corrections", type=save_button_type, use_container_width=True, disabled=(completed == 0)):
        if completed == 0:
            st.error("No completed corrections to save")
            st.stop()
        
        # Prepare only completed corrections
        corrections = []
        keys_to_remove = []
        
        for error_key, correction_data in st.session_state.all_corrections_data.items():
            explanation = correction_data.get('explanation', '').strip()
            
            # Skip if no explanation
            if not explanation:
                continue
            
            # Skip if out of range without detailed explanation
            if correction_data.get('outside_range', False) and len(explanation) < 20:
                continue
            
            # Skip if differs from both without good explanation
            if correction_data.get('differs_from_both', False) and len(explanation) < 15:
                continue
            
            # This correction is valid, include it
            error_data = correction_data['error_data']
            error_id_col = correction_data.get('id_column', id_col)
            
            base_record = {
                'error_type': correction_data['error_type'],
                'username': error_data.get('username', ''),
                'supervisor': error_data.get('supervisor', ''),
                'woreda': error_data.get('woreda', ''),
                'kebele': error_data.get('kebele', ''),
                'farmer_name': error_data.get('farmer_name', ''),
                'phone_no': error_data.get('phone_no', ''),
                'subdate': error_data.get('subdate', ''),
                'unique_id': error_data.get(error_id_col, ''),
                'variable': error_data.get('variable', ''),
                'original_value': error_data.get('value', ''),
                'correct_value': correction_data['correct_value'],
                'explanation': correction_data['explanation'],
                'corrected_by': selected_enumerator,
                'correction_date': datetime.now().strftime("%d-%b-%y"),
                'correction_timestamp': datetime.now().isoformat(),
                'outside_range': correction_data.get('outside_range', False),
                'differs_from_both': correction_data.get('differs_from_both', False)
            }
            
            if correction_data['error_type'] == 'constraint':
                base_record['reference_value'] = error_data.get('constraint', '')
            else:
                base_record['reference_value'] = error_data.get('Troster Value', '')
            
            corrections.append(base_record)
            keys_to_remove.append(error_key)
        
        if corrections:
            corrections_df = pd.DataFrame(corrections)
            
            with st.spinner("Saving to secure repository..."):
                if save_corrections_to_github(corrections_df):
                    st.success(f"✅ Successfully saved {len(corrections)} corrections!")
                    if total - completed > 0:
                        st.info(f"📝 {total - completed} items still need attention and were not saved.")
                    st.balloons()
                    
                    # Mark as corrected and remove from pending
                    for error_key in keys_to_remove:
                        st.session_state.corrected_errors.add(error_key)
                        if error_key in st.session_state.all_corrections_data:
                            del st.session_state.all_corrections_data[error_key]
                    
                    # Clear cache to reload data
                    load_data_from_github.clear()
                    st.rerun()
                else:
                    st.error("❌ Failed to save. Please try again or contact support.")
        else:
            st.warning("No completed corrections to save.")

# ============================================================================
# ADMIN LOGIN
# ============================================================================

def render_admin_login():
    """Render admin login in sidebar"""
    st.sidebar.header("🔐 Admin Access")
    
    with st.sidebar.form("admin_login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login", use_container_width=True)
        
        if submit:
            if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
                st.session_state.is_admin = True
                st.rerun()
            else:
                st.error("Invalid credentials")

# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    """Main application entry point"""
    
    # Check token validity
    with st.spinner("Verifying access..."):
        if not check_token_validity():
            st.stop()
    
    # Load data
    with st.spinner("Loading data from secure repository..."):
        constraints_df, logic_df = load_data_from_github()
    
    if constraints_df is None or logic_df is None:
        st.error("❌ Could not load data from repository")
        st.info("""
            **Troubleshooting:**
            1. Check GitHub token is valid
            2. Verify files exist in repository
            3. Check internet connection
            4. Contact administrator if issue persists
        """)
        st.stop()
    
    # Route to appropriate interface
    if st.session_state.is_admin:
        render_admin_dashboard(constraints_df, logic_df)
    else:
        render_admin_login()
        render_enumerator_interface(constraints_df, logic_df)
    
    # Footer
    st.markdown("---")
    st.markdown(
        "<p style='text-align: center; color: #666;'>📱 HFC Correction System v2.0 | "
        f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>",
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()