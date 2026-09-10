with open('ui/static/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

required_elements = [
    'sidebar', 'main-content', 'stats-grid', 'patients-grid', 'patients-list',
    'prescriptions-list', 'doctors-list', 'pharmacies-list', 'caregiver-select',
    'modal-overlay', 'toast-container', 'confirm-modal', 'alert-modal',
    'patient-modal', 'prescription-modal', 'doctor-modal', 'pharmacy-modal',
    'page-title', 'add-btn', 'caregiver-email', 'caregiver-timezone',
    'caregiver-info', 'meds-patient-name', 'pharmacy-patient-name',
]

for elem_id in required_elements:
    found = ('id="' + elem_id + '"' in content) or ("id='" + elem_id + "'" in content)
    status = 'OK' if found else 'MISSING'
    print(f'{status}: {elem_id}')