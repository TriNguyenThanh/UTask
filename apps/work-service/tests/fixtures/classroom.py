from infrastructure.classroom import GroupMemberFact, GroupSnapshot


class FixtureClassroom:
    groups = {}
    teachers = {}

    def group_snapshot(self, group_id, actor):
        return self.groups[group_id]

    def teacher_group_ids(self, actor):
        return self.teachers.get(actor.id, [])


__all__ = ["FixtureClassroom", "GroupMemberFact", "GroupSnapshot"]
