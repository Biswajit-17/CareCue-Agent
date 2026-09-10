"""CareCue Streamlit UI - Setup Wizard for Caregivers."""

import streamlit as st
import pandas as pd
from datetime import date, datetime
from typing import Optional

# Add project root to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.repository import get_repository
from data.models import (
    Caregiver, Patient, Doctor, Pharmacy, Prescription,
    Frequency, RefillStatus
)
from tools.conflict_checker import conflict_checker
from tools.dose_pattern_checker import dose_pattern_checker


# --- Page Config & Custom CSS ---

st.set_page_config(
    page_title="CareCue - Medication Logistics",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for visual polish
st.markdown("""
<style>
    /* Card styling */
    .stContainer > div {
        border-radius: 12px;
    }
    
    /* Metric cards */
    [data-testid="metric-container"] {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        padding: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    
    /* Alert cards */
    .alert-card {
        padding: 16px;
        border-radius: 10px;
        margin-bottom: 12px;
        border-left: 4px solid;
    }
    .alert-high { border-color: #dc2626; background: #fef2f2; }
    .alert-medium { border-color: #ea580c; background: #fff7ed; }
    .alert-low { border-color: #2563eb; background: #eff6ff; }
    .alert-ok { border-color: #16a34a; background: #f0fdf4; }
    
    /* Prescription cards */
    .rx-card {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 12px;
    }
    
    /* Conflict highlight */
    .conflict-badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
        margin-right: 8px;
    }
    .conflict-high { background: #fef2f2; color: #dc2626; }
    .conflict-medium { background: #fff7ed; color: #ea580c; }
    
    /* Sidebar */
    .css-1d391kg { padding-top: 2rem; }
    
    /* Hide streamlit branding */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    
    /* Button styling */
    .stButton > button {
        border-radius: 8px;
        font-weight: 500;
    }
    
    /* Form inputs */
    .stTextInput > div > div > input,
    .stNumberInput > div > div > input,
    .stSelectbox > div > div > div {
        border-radius: 8px;
    }
    
    /* Expander */
    .streamlit-expanderHeader {
        font-weight: 600;
        font-size: 16px;
    }
</style>
""", unsafe_allow_html=True)


# Initialize repository
repo = get_repository()


# --- Helper Functions ---

def get_or_create_caregiver(email: str, name: str, phone: str = "", timezone: str = "UTC") -> Caregiver:
    """Get existing caregiver by email or create new."""
    caregiver = repo.get_caregiver_by_email(email)
    if not caregiver:
        caregiver = Caregiver(name=name, email=email, phone=phone, timezone=timezone)
        repo.create_caregiver(caregiver)
    return caregiver


def render_sidebar():
    """Render sidebar with caregiver selection."""
    with st.sidebar:
        st.markdown("### 💊 CareCue")
        st.caption("Medication Logistics for Caregivers")
        st.divider()
        
        caregivers = repo.list_caregivers()
        
        if not caregivers:
            st.info("No caregivers yet. Create one below.")
            return None
        
        caregiver_options = {f"{c.name} ({c.email})": c for c in caregivers}
        selected = st.selectbox(
            "Active Caregiver",
            options=list(caregiver_options.keys()),
            index=0,
            label_visibility="collapsed"
        )
        
        caregiver = caregiver_options[selected]
        
        st.caption(f"📧 {caregiver.email}")
        st.caption(f"🕐 {caregiver.timezone}")
        
        return caregiver


def render_caregiver_setup():
    """Render caregiver creation form."""
    st.markdown("### 👤 Caregiver Setup")
    st.write("Enter your information to get started.")
    
    with st.form("caregiver_form", border=True):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Your Name", placeholder="Sarah Thompson")
            email = st.text_input("Email", placeholder="your@email.com")
        with col2:
            phone = st.text_input("Phone (optional)", placeholder="+1-555-0199")
            timezone = st.selectbox(
                "Timezone",
                options=["UTC", "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles"],
                index=1
            )
        
        submitted = st.form_submit_button("Create Caregiver", type="primary", use_container_width=True)
        
        if submitted:
            if not name or not email:
                st.error("Name and email are required")
            else:
                caregiver = get_or_create_caregiver(email, name, phone, timezone)
                st.success(f"Caregiver created: {caregiver.name}")
                st.rerun()


def render_patient_management(caregiver: Caregiver):
    """Render patient management section."""
    st.markdown("### 👴 Patients")
    
    patients = repo.get_patients_by_caregiver(caregiver.id)
    
    # Add new patient
    with st.expander("➕ Add New Patient", expanded=len(patients) == 0):
        with st.form("patient_form", border=True):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Patient Name", placeholder="Margaret Thompson")
                dob = st.date_input(
                    "Date of Birth",
                    value=date(1942, 3, 15),
                    min_value=date(1900, 1, 1),
                    max_value=date.today()
                )
            with col2:
                notes = st.text_area("Notes", placeholder="Lives independently, mild cognitive impairment")
            
            submitted = st.form_submit_button("Add Patient", type="primary", use_container_width=True)
            
            if submitted:
                if not name:
                    st.error("Patient name is required")
                else:
                    patient = Patient(
                        caregiver_id=caregiver.id,
                        name=name,
                        date_of_birth=dob,
                        notes=notes or None
                    )
                    repo.create_patient(patient)
                    st.success(f"Patient added: {patient.name}")
                    st.rerun()
    
    # List patients
    if patients:
        for patient in patients:
            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 2, 1])
                with col1:
                    st.markdown(f"#### {patient.name} (age {patient.age})")
                    if patient.notes:
                        st.caption(patient.notes)
                with col2:
                    st.write(f"📅 DOB: {patient.date_of_birth}")
                with col3:
                    if st.button("Manage Medications", key=f"manage_{patient.id}", use_container_width=True):
                        st.session_state.selected_patient = patient.id
                        st.rerun()
                
                # Show prescriptions summary
                rx_list = repo.get_prescriptions_by_patient(patient.id)
                if rx_list:
                    st.write(f"**{len(rx_list)} active prescriptions**")
                    for rx in rx_list:
                        status = "🔴" if rx.is_refill_overdue else ("🟡" if rx.is_refill_due_soon() else "🟢")
                        st.write(f"  {status} {rx.medication_name} {rx.strength} — {rx.frequency.value} — refill due: {rx.next_refill_due or 'N/A'}")
                else:
                    st.info("No prescriptions yet")


def render_prescription_management(patient_id: str):
    """Render prescription management for a patient."""
    patient = repo.get_patient(patient_id)
    if not patient:
        st.error("Patient not found")
        return
    
    st.markdown(f"### 💊 Medications for {patient.name}")
    
    col_back, col_space = st.columns([1, 5])
    with col_back:
        if st.button("← Back to Patients", use_container_width=True):
            if 'selected_patient' in st.session_state:
                del st.session_state.selected_patient
            st.rerun()
    
    # Add prescription
    doctors = repo.list_doctors()
    pharmacies = repo.get_pharmacies_by_patient(patient_id)
    
    with st.expander("➕ Add Prescription", expanded=True):
        if not doctors:
            st.warning("No doctors added yet. Add a doctor in the Doctors tab first.")
        if not pharmacies:
            st.warning("No pharmacy added yet. Add a pharmacy in the Pharmacies tab first.")
        
        if doctors and pharmacies:
            with st.form("prescription_form", border=True):
                col1, col2 = st.columns(2)
                
                with col1:
                    medication_name = st.text_input("Medication Name*", placeholder="Lisinopril")
                    generic_name = st.text_input("Generic Name", placeholder="Lisinopril")
                    strength = st.text_input("Strength*", placeholder="10mg")
                    form = st.selectbox("Form", ["tablet", "capsule", "liquid", "patch", "injection", "other"])
                    route = st.selectbox("Route", ["oral", "topical", "sublingual", "inhalation", "injection", "other"])
                
                with col2:
                    doctor = st.selectbox(
                        "Prescribing Doctor*",
                        options=doctors,
                        format_func=lambda d: f"{d.name} ({d.specialty or 'General'})"
                    )
                    pharmacy = st.selectbox(
                        "Pharmacy*",
                        options=pharmacies,
                        format_func=lambda p: f"{p.name} - {p.phone}"
                    )
                    dose_amount = st.number_input("Dose Amount*", min_value=0.1, value=1.0, step=0.5)
                    dose_unit = st.selectbox("Dose Unit", ["tablet", "capsule", "ml", "mg", "patch", "unit"])
                
                col3, col4 = st.columns(2)
                with col3:
                    frequency = st.selectbox(
                        "Frequency*",
                        options=list(Frequency),
                        format_func=lambda f: f.value.replace('_', ' ').title()
                    )
                    frequency_hours = st.number_input(
                        "Custom Hours (if not standard)",
                        min_value=1, max_value=24, value=24,
                        help="Only used for custom intervals"
                    )
                    refill_cycle_days = st.number_input("Refill Cycle (days)*", min_value=1, value=30)
                
                with col4:
                    refills_remaining = st.number_input("Refills Remaining", min_value=0, value=3)
                    total_refills_allowed = st.number_input("Total Refills Allowed", min_value=0, value=5)
                    last_filled = st.date_input("Last Filled Date", value=date.today())
                    start_date = st.date_input("Prescription Start Date", value=date.today())
                
                instructions = st.text_area("Instructions", placeholder="Take in the morning with food")
                
                col5, col6 = st.columns(2)
                with col5:
                    ndc_code = st.text_input("NDC Code (optional)", placeholder="00093-7272-98")
                with col6:
                    rxnorm_cui = st.text_input("RxNorm CUI (optional)", placeholder="197361")
                
                submitted = st.form_submit_button("Add Prescription", type="primary", use_container_width=True)
                
                if submitted:
                    if not medication_name or not strength or not doctor:
                        st.error("Medication name, strength, and doctor are required")
                    else:
                        from datetime import timedelta
                        next_refill = last_filled + timedelta(days=refill_cycle_days)
                        
                        prescription = Prescription(
                            patient_id=patient_id,
                            doctor_id=doctor.id,
                            pharmacy_id=pharmacy.id,
                            medication_name=medication_name,
                            generic_name=generic_name or None,
                            strength=strength,
                            form=form,
                            route=route,
                            dose_amount=dose_amount,
                            dose_unit=dose_unit,
                            frequency=frequency,
                            frequency_hours=frequency_hours if frequency == Frequency.PRN else None,
                            instructions=instructions or None,
                            refill_cycle_days=refill_cycle_days,
                            refills_remaining=refills_remaining,
                            total_refills_allowed=total_refills_allowed,
                            last_filled_date=last_filled,
                            next_refill_due=next_refill,
                            prescription_start_date=start_date,
                            ndc_code=ndc_code or None,
                            rxnorm_cui=rxnorm_cui or None,
                        )
                        repo.create_prescription(prescription)
                        st.success(f"Prescription added: {medication_name} {strength}")
                        st.rerun()
    
    # List prescriptions
    prescriptions = repo.get_prescriptions_by_patient(patient_id)
    
    if prescriptions:
        st.markdown("#### Current Prescriptions")
        
        # Check for duplicate generics to show note
        generic_groups = {}
        for rx in prescriptions:
            if rx.generic_name:
                generic_groups.setdefault(rx.generic_name.lower(), []).append(rx)
        
        duplicate_generics = {k: v for k, v in generic_groups.items() if len(v) > 1}
        if duplicate_generics:
            st.info("ℹ️ **Note:** Some medications share the same generic ingredient (e.g., Lisinopril/Prinivil). This is intentional realism — it happens when different doctors prescribe brand vs. generic. The conflict checker flags this automatically.")
        
        for rx in prescriptions:
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
                
                with col1:
                    st.markdown(f"**{rx.medication_name}** {rx.strength}")
                    if rx.generic_name and rx.generic_name != rx.medication_name:
                        st.caption(f"Generic: {rx.generic_name}")
                    st.caption(f"{rx.dose_amount} {rx.dose_unit} • {rx.frequency.value}")
                    if rx.instructions:
                        st.caption(rx.instructions)
                
                with col2:
                    doctor = repo.get_doctor(rx.doctor_id)
                    pharmacy = repo.get_pharmacy(rx.pharmacy_id)
                    st.write(f"**Doctor:** {doctor.name if doctor else 'Unknown'}")
                    if doctor and doctor.specialty:
                        st.caption(doctor.specialty)
                    st.write(f"**Pharmacy:** {pharmacy.name if pharmacy else 'Unknown'}")
                
                with col3:
                    if rx.is_refill_overdue:
                        status_class = "alert-high"
                        status_text = "🔴 OVERDUE"
                    elif rx.is_refill_due_soon():
                        status_class = "alert-medium"
                        status_text = "🟡 DUE SOON"
                    else:
                        status_class = "alert-ok"
                        status_text = "🟢 OK"
                    
                    st.markdown(f"<div class='alert-card {status_class}'><strong>Refill Status:</strong> {status_text}</div>", unsafe_allow_html=True)
                    
                    if rx.next_refill_due:
                        days = rx.days_until_refill
                        if days is not None:
                            if days < 0:
                                st.write(f"{abs(days)} days overdue")
                            elif days == 0:
                                st.write("Due today!")
                            else:
                                st.write(f"Due in {days} days")
                    st.write(f"Refills left: {rx.refills_remaining}/{rx.total_refills_allowed}")
                
                with col4:
                    if st.button("🗑️ Discontinue", key=f"delete_rx_{rx.id}", use_container_width=True):
                        rx.is_active = False
                        rx.discontinued_date = date.today()
                        rx.discontinuation_reason = "Discontinued via UI"
                        repo.update_prescription(rx)
                        st.rerun()
    else:
        st.info("No prescriptions yet. Add one above.")


def render_doctors():
    """Render doctor management."""
    st.markdown("### 👨‍⚕️ Doctors")
    
    doctors = repo.list_doctors()
    
    with st.expander("➕ Add Doctor", expanded=len(doctors) == 0):
        with st.form("doctor_form", border=True):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Doctor Name*", placeholder="Dr. James Cardiology")
                specialty = st.text_input("Specialty", placeholder="Cardiology")
                practice = st.text_input("Practice Name", placeholder="Heart Health Associates")
            with col2:
                phone = st.text_input("Phone", placeholder="+1-555-0101")
                fax = st.text_input("Fax", placeholder="+1-555-0102")
                email = st.text_input("Email", placeholder="cardiology@hearthealth.example.com")
            
            address = st.text_input("Address", placeholder="100 Medical Plaza, Suite 200")
            notes = st.text_area("Notes", placeholder="Primary cardiologist")
            
            submitted = st.form_submit_button("Add Doctor", type="primary", use_container_width=True)
            
            if submitted:
                if not name:
                    st.error("Doctor name is required")
                else:
                    doctor = Doctor(
                        name=name, specialty=specialty or None,
                        practice_name=practice or None, phone=phone or None,
                        fax=fax or None, email=email or None,
                        address=address or None, notes=notes or None
                    )
                    repo.create_doctor(doctor)
                    st.success(f"Doctor added: {doctor.name}")
                    st.rerun()
    
    if doctors:
        for doctor in doctors:
            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 2, 1])
                with col1:
                    st.markdown(f"**{doctor.name}**")
                    if doctor.specialty:
                        st.caption(f"{doctor.specialty} • {doctor.practice_name or ''}")
                with col2:
                    st.write(f"📞 {doctor.phone or 'N/A'}  📧 {doctor.email or 'N/A'}")
                with col3:
                    rx_count = len(repo.get_prescriptions_by_doctor(doctor.id))
                    st.write(f"{rx_count} prescriptions")


def render_pharmacies(patient_id: str):
    """Render pharmacy management for a patient."""
    patient = repo.get_patient(patient_id)
    if not patient:
        return
    
    st.markdown("### 🏪 Pharmacies")
    
    pharmacies = repo.get_pharmacies_by_patient(patient_id)
    
    with st.expander("➕ Add Pharmacy", expanded=len(pharmacies) == 0):
        with st.form("pharmacy_form", border=True):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Pharmacy Name*", placeholder="Community Pharmacy")
                phone = st.text_input("Phone*", placeholder="+1-555-0301")
                address = st.text_input("Address", placeholder="500 Main St")
            with col2:
                fax = st.text_input("Fax", placeholder="+1-555-0302")
                email = st.text_input("Email", placeholder="pharmacy@example.com")
                hours = st.text_input("Hours", placeholder="Mon-Fri 9-8, Sat 9-5, Sun 10-2")
            
            is_preferred = st.checkbox("Preferred Pharmacy", value=True)
            
            submitted = st.form_submit_button("Add Pharmacy", type="primary", use_container_width=True)
            
            if submitted:
                if not name or not phone:
                    st.error("Name and phone are required")
                else:
                    pharmacy = Pharmacy(
                        patient_id=patient_id, name=name, phone=phone,
                        address=address or None, fax=fax or None,
                        email=email or None, hours=hours or None,
                        is_preferred=is_preferred
                    )
                    repo.create_pharmacy(pharmacy)
                    st.success(f"Pharmacy added: {pharmacy.name}")
                    st.rerun()
    
    if pharmacies:
        for pharmacy in pharmacies:
            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 2, 1])
                with col1:
                    st.markdown(f"**{pharmacy.name}** {'⭐' if pharmacy.is_preferred else ''}")
                    if pharmacy.address:
                        st.caption(pharmacy.address)
                with col2:
                    st.write(f"📞 {pharmacy.phone}  📠 {pharmacy.fax or 'N/A'}")
                    if pharmacy.hours:
                        st.caption(f"Hours: {pharmacy.hours}")
                with col3:
                    if not pharmacy.is_preferred:
                        if st.button("Make Preferred", key=f"pref_{pharmacy.id}", use_container_width=True):
                            st.rerun()


def render_dashboard(caregiver: Caregiver):
    """Render main dashboard with alerts summary."""
    st.markdown("### 📊 Dashboard")
    
    patients = repo.get_patients_by_caregiver(caregiver.id)
    
    if not patients:
        st.info("Add a patient to get started")
        return
    
    # Collect all alerts across patients
    total_refills_due = 0
    total_overdue = 0
    total_conflicts = 0
    total_low_adherence = 0
    
    patient_summaries = []
    
    for patient in patients:
        # Refills
        refill_result = repo.get_prescriptions_by_patient(patient.id)
        patient_overdue = 0
        patient_due = 0
        for rx in refill_result:
            if rx.is_refill_overdue:
                patient_overdue += 1
                total_overdue += 1
            elif rx.is_refill_due_soon():
                patient_due += 1
                total_refills_due += 1
        
        # Conflicts
        conflict_result = conflict_checker(patient.id)
        patient_conflicts = conflict_result["conflicts_found"]
        total_conflicts += patient_conflicts
        
        # Dose patterns
        pattern_result = dose_pattern_checker(patient.id)
        patient_adherence = pattern_result.get("adherence_rate", 100)
        patient_low_adherence = 1 if patient_adherence < 80 else 0
        total_low_adherence += patient_low_adherence
        
        patient_summaries.append({
            "patient": patient,
            "overdue": patient_overdue,
            "due": patient_due,
            "conflicts": patient_conflicts,
            "conflict_details": conflict_result["conflicts"],
            "adherence": patient_adherence,
            "missed_streaks": pattern_result.get("missed_streaks", []),
            "prescriptions": refill_result
        })
    
    # Top metrics row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("🔴 Overdue Refills", total_overdue, delta="Needs attention" if total_overdue > 0 else None, delta_color="inverse")
    with col2:
        st.metric("🟡 Refills Due Soon", total_refills_due)
    with col3:
        st.metric("⚠️ Medication Conflicts", total_conflicts, delta="Review needed" if total_conflicts > 0 else None, delta_color="inverse")
    with col4:
        st.metric("📉 Low Adherence", total_low_adherence)
    
    st.divider()
    
    # Patient cards
    for summary in patient_summaries:
        patient = summary["patient"]
        
        with st.container(border=True):
            # Header with patient name and quick actions
            col_header, col_action = st.columns([4, 1])
            with col_header:
                st.markdown(f"#### {patient.name} (age {patient.age})")
            with col_action:
                if st.button("Manage Meds", key=f"dash_manage_{patient.id}", use_container_width=True):
                    st.session_state.selected_patient = patient.id
                    st.rerun()
            
            col1, col2, col3 = st.columns(3)
            
            # Column 1: Prescriptions with status
            with col1:
                st.markdown("**Prescriptions**")
                if summary["prescriptions"]:
                    for rx in summary["prescriptions"]:
                        status_icon = "🔴" if rx.is_refill_overdue else ("🟡" if rx.is_refill_due_soon() else "🟢")
                        generic_note = f" (generic: {rx.generic_name})" if rx.generic_name and rx.generic_name != rx.medication_name else ""
                        st.write(f"{status_icon} {rx.medication_name} {rx.strength}{generic_note}")
                        if rx.next_refill_due:
                            days = rx.days_until_refill
                            if days is not None and days <= 7:
                                label = "overdue" if days < 0 else f"{days} days"
                                st.caption(f"Refill: {rx.next_refill_due} ({label})")
                else:
                    st.write("None")
            
            # Column 2: Conflicts - THE KEY DEMO SCREEN
            with col2:
                st.markdown("**⚠️ Conflicts Detected**")
                if summary["conflicts"] > 0:
                    for c in summary["conflict_details"]:
                        severity_class = "conflict-high" if c["severity"] == "high" else "conflict-medium"
                        st.markdown(f"""
                        <div class='alert-card alert-{c["severity"]}'>
                            <span class='conflict-badge {severity_class}'>{c["type"].replace('_', ' ').title()}</span>
                            <strong>{c["message"]}</strong>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.success("No conflicts detected")
            
            # Column 3: Adherence
            with col3:
                st.markdown("**Adherence (30 days)**")
                adherence = summary["adherence"]
                if adherence >= 90:
                    st.success(f"{adherence:.0f}%")
                elif adherence >= 70:
                    st.warning(f"{adherence:.0f}%")
                else:
                    st.error(f"{adherence:.0f}%")
                
                if summary["missed_streaks"]:
                    for streak in summary["missed_streaks"]:
                        st.markdown(f"""
                        <div class='alert-card alert-high'>
                            <strong>{streak['medication']}</strong>: {streak['consecutive_missed']} consecutive missed doses
                        </div>
                        """, unsafe_allow_html=True)


# --- Main App ---

def main():
    st.title("💊 CareCue - Medication Logistics for Caregivers")
    st.caption("Tracks refills, detects conflicts, monitors adherence — only alerts when decisions needed")
    
    # Sidebar
    caregiver = render_sidebar()
    
    # Main content
    if caregiver is None:
        render_caregiver_setup()
    else:
        # Navigation tabs
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📊 Dashboard", "👴 Patients", "💊 Medications", "👨‍⚕️ Doctors", "🏪 Pharmacies"
        ])
        
        with tab1:
            render_dashboard(caregiver)
        
        with tab2:
            render_patient_management(caregiver)
        
        with tab3:
            if 'selected_patient' in st.session_state:
                render_prescription_management(st.session_state.selected_patient)
            else:
                st.info("👈 Select a patient from the **Dashboard** or **Patients** tab to manage their medications")
        
        with tab4:
            render_doctors()
        
        with tab5:
            if 'selected_patient' in st.session_state:
                render_pharmacies(st.session_state.selected_patient)
            else:
                st.info("👈 Select a patient to manage their pharmacies")


if __name__ == "__main__":
    main()