import { createInitialDatabase, type MockDatabase } from "@/mocks/data/database";
import type { MockScenario } from "@/mocks/scenarios";

/**
 * Storage layout version. Bump and write a migration below whenever the
 * persisted `MockDatabase` shape changes, so older demo sessions restore
 * cleanly instead of crashing on missing fields.
 */
const DB_VERSION = 3;
const DB_KEY_PREFIX = "utask.mock.db.v3:";
const memoryFallback = new Map<string, MockDatabase>();

export interface MockRepository {
  db: MockDatabase;
  save(): void;
}

interface StoredDb {
  version?: number;
  db?: unknown;
}

/**
 * Fills in fields missing from an older persisted layout. Mutates in place
 * and returns the same object so callers keep one reference.
 */
function migrate(old: unknown): MockDatabase {
  const fresh = createInitialDatabase("default");
  const record = (old ?? {}) as Partial<MockDatabase>;
  const migrated: MockDatabase = {
    ...fresh,
    ...record,
    profilesByUser: { ...fresh.profilesByUser, ...record.profilesByUser },
    authUsersById: { ...fresh.authUsersById, ...record.authUsersById },
    createdTeams: record.createdTeams ?? fresh.createdTeams,
    notificationReadByUser: record.notificationReadByUser ?? fresh.notificationReadByUser,
    githubDisconnectedByUser:
      record.githubDisconnectedByUser ?? fresh.githubDisconnectedByUser,
    aiConfigByProject: record.aiConfigByProject ?? fresh.aiConfigByProject,
  };
  return migrated;
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
    if (stored) {
      const parsed = JSON.parse(stored) as StoredDb;
      db = parsed.version === DB_VERSION ? migrate(parsed.db) : createInitialDatabase(scenario);
    } else {
      db = createInitialDatabase(scenario);
    }
  } catch {
    storageAvailable = false;
    db = memoryFallback.get(key) ?? createInitialDatabase(scenario);
  }

  const repository: MockRepository = {
    db,
    save() {
      if (storageAvailable) {
        try {
          sessionStorage.setItem(
            key,
            JSON.stringify({ version: DB_VERSION, db: repository.db }),
          );
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