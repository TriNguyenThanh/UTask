from uuid import uuid4
import pytest
from apps.courses.models import ClassSection, ClassTeacher
pytestmark = [pytest.mark.django_db, pytest.mark.contract]

def test_class_creation_replay_returns_original_class(class_creation_payload, client_for, actors, post_command):
    teacher = client_for(actors['teacher'])
    key = uuid4()
    response = post_command(teacher, '/classes/', class_creation_payload, key)
    assert response.status_code == 201, response.content
    data = response.json()['data']
    assert data['code'] == 'SE02' and 'join_code_hash' not in data
    assert ClassTeacher.objects.filter(class_section_id=data['id'], user_id=actors['teacher'], role='PRIMARY').exists()
    assert post_command(teacher, '/classes/', class_creation_payload, key).json() == response.json()
    assert ClassSection.objects.filter(code='SE02').count() == 1

def test_class_creation_rejects_changed_payload_for_same_key(class_creation_payload, client_for, actors, post_command):
    teacher = client_for(actors['teacher'])
    key = uuid4()
    assert post_command(teacher, '/classes/', class_creation_payload, key).status_code == 201
    conflict = post_command(teacher, '/classes/', {**class_creation_payload, 'name': 'Khác'}, key)
    assert conflict.status_code == 422
    assert ClassSection.objects.get(code='SE02').name == class_creation_payload['name']

def test_class_creation_rejects_invalid_date_range(class_creation_payload, client_for, actors, post_command):
    response = post_command(client_for(actors['teacher']), '/classes/', {**class_creation_payload, 'starts_on': '2027-01-01'})
    assert response.status_code == 400 and response.json()['error']['details']
    assert not ClassSection.objects.filter(code='SE02').exists()

def test_student_cannot_create_class(class_creation_payload, client_for, actors, post_command):
    response = post_command(client_for(actors['leader']), '/classes/', class_creation_payload)
    assert response.status_code == 403
    assert not ClassSection.objects.filter(code='SE02').exists()

def test_unrelated_user_cannot_read_class(section, client_for):
    assert client_for(uuid4()).get(f'/classes/{section.pk}/').status_code == 404
