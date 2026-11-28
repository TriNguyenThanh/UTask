from django.db import connection


def allocate_sequences(project, count):
    """Caller holds the Project barrier; allocation rolls back with the batch."""
    if not connection.in_atomic_block or count < 1:
        raise ValueError("Allocation requires a locked Project and a positive batch size")
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE projects SET current_task_sequence = current_task_sequence + %s "
            "WHERE id = %s RETURNING current_task_sequence",
            [count, project.pk],
        )
        end = cursor.fetchone()[0]
    project.current_task_sequence = end
    return range(end - count + 1, end + 1)
