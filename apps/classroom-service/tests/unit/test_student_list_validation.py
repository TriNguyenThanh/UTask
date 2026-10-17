import pytest

from apps.courses.serializers.enrollments import StudentListSerializer

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("count", [1, 100])
def test_student_list_accepts_boundary_sizes_for_per_row_provisioning(count):
    # Row validation belongs to provisioning so one invalid email does not reject the batch.
    students = [{"email": "invalid-email"}] * count
    serializer = StudentListSerializer(data={"students": students})

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data == {"students": students}


@pytest.mark.parametrize(
    "count, code, issue",
    [
        (0, "min_length", "Danh sách phải có ít nhất 1 sinh viên."),
        (101, "max_length", "Mỗi yêu cầu chỉ được chứa tối đa 100 sinh viên."),
    ],
)
def test_student_list_rejects_invalid_size_with_specific_vietnamese_issue(count, code, issue):
    serializer = StudentListSerializer(
        data={"students": [{"email": "student@example.test"}] * count}
    )

    assert not serializer.is_valid()
    assert str(serializer.errors["students"][0]) == issue
    assert serializer.errors["students"][0].code == code
