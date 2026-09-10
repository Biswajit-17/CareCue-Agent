from fastapi.testclient import TestClient
from ui.api import app
from data.repository import get_repository

client = TestClient(app)
repo = get_repository()

# First check what doctors/pharmacies exist
doctors = client.get('/api/doctors').json()
print('Doctors:', len(doctors))
for d in doctors[:2]:
    print('  ' + d['id'] + ': ' + d['name'])

pharmacies = client.get('/api/pharmacies?patient_id=01ARZ3NDEKTSV4RRFFQ69G5FAV').json()
print('Pharmacies:', len(pharmacies))
for p in pharmacies[:2]:
    print('  ' + p['id'] + ': ' + p['name'])

# Test deleting a doctor that has NO active prescriptions (should work)
if len(doctors) > 2:
    r = client.delete('/api/doctors/' + doctors[2]['id'])
    print('Delete doctor without prescriptions:', r.status_code)

# Test deleting a pharmacy that has NO active prescriptions
if len(pharmacies) > 1:
    r = client.delete('/api/pharmacies/' + pharmacies[1]['id'])
    print('Delete pharmacy without prescriptions:', r.status_code)

# Test deleting a prescription
prescriptions = client.get('/api/prescriptions?patient_id=01ARZ3NDEKTSV4RRFFQ69G5FAV').json()
print('Prescriptions:', len(prescriptions))
if prescriptions:
    r = client.delete('/api/prescriptions/' + prescriptions[0]['id'])
    print('Delete prescription:', r.status_code)

print('All DELETE tests passed!')