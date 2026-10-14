import pytest

from infrastructure.storage import ObjectFacts


class FixtureStorage:
    objects = {}
    deletes = []

    def presign(self, row):
        return "https://storage.test/put/" + str(row.pk), {"If-None-Match": "*"}

    def inspect(self, row):
        return self.objects.get(row.storage_key, ObjectFacts(row.file_size, row.content_type, True))

    def download(self, row):
        return "https://storage.test/get/" + str(row.pk)

    def delete(self, key):
        self.deletes.append(key)


@pytest.fixture
def storage(settings):
    settings.WORK_STORAGE_ADAPTER = "tests.fixtures.storage.FixtureStorage"
    FixtureStorage.objects = {}
    FixtureStorage.deletes = []
    return FixtureStorage
