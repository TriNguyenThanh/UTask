import { createInitialDatabase, type MockDatabase } from "@/mocks/data/database";
import type { MockScenario } from "@/mocks/scenarios";

const DB_KEY_PREFIX = "utask.mock.db.v2:";
const memoryFallback = new Map<string, MockDatabase>();

export interface MockRepository {
  db: MockDatabase;
  save(): void;
}

export function createMemoryRepository(scenario: MockScenario): MockRepository {
  return {
    db: createInitialDatabase(scenario),
    save: () => undefined,
  };
}

export function createBrowserRepository(scenario: MockScenario): MockRepository {
  const key = `${DB_KEY_PREFIX}${scenario}`;
  let storageAvailable = true;
  let db: MockDatabase;

  try {
    const stored = sessionStorage.getItem(key);
    db = stored ? JSON.parse(stored) as MockDatabase : createInitialDatabase(scenario);
  } catch {
    storageAvailable = false;
    db = memoryFallback.get(key) ?? createInitialDatabase(scenario);
  }

  const repository: MockRepository = {
    db,
    save() {
      if (storageAvailable) {
        try {
          sessionStorage.setItem(key, JSON.stringify(repository.db));
          return;
        } catch {
          storageAvailable = false;
        }
      }
      memoryFallback.set(key, repository.db);
    },
  };

  if (!storageAvailable) {
    memoryFallback.set(key, db);
  }
  return repository;
}
