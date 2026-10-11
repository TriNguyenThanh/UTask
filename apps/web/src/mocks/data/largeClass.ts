/**
 * A class of 100 students for trying the Teacher screens at scale: long
 * tables, many teams, filters that actually filter. Generated, not typed in,
 * and deterministic (no randomness), so tests and screenshots are stable.
 *
 * Only the instructor can sign in (`teacher3@utask.test`). The students are
 * roster entries with no account. This module imports nothing from the
 * graph or the directory; they import it and merge the result in.
 */

export const LARGE_COURSE_ID = "course-se360-large";
export const LARGE_STUDENT_COUNT = 100;

const id = (n: number) => `00000000-0000-4000-8000-${n.toString(16).padStart(12, "0")}`;

const FAMILY = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Vũ", "Đặng", "Bùi", "Đỗ", "Ngô"];
const MIDDLE = ["Văn", "Thị", "Minh", "Quốc", "Thanh"];
const GIVEN = ["An", "Bình", "Châu", "Dũng", "Giang", "Hà", "Khánh", "Lan", "Nam", "Phúc"];
const SKILLS = ["Frontend React", "Backend Node.js", "Database", "QA", "UI/UX", "DevOps"];
const TEAM_NAMES = [
  "Alpha", "Beacon", "Cobalt", "Delta", "Ember", "Falcon", "Gamma", "Helix", "Ion", "Jade",
  "Kepler", "Lumen", "Meteor", "Nova", "Orbit", "Pulse", "Quasar", "Rocket", "Spark",
];

export interface LargeStudent {
  userId: string;
  displayName: string;
  studentCode: string;
  email: string;
  skill: string;
}

/** Student `i` (0-based): the family/given pair is unique across all 100. */
export const LARGE_STUDENTS: readonly LargeStudent[] = Array.from(
  { length: LARGE_STUDENT_COUNT },
  (_, i) => {
    const code = `2102${(1000 + i).toString()}`;
    return {
      userId: id(0x1000 + i),
      displayName: `${FAMILY[i % 10]} ${MIDDLE[(i * 3) % MIDDLE.length]} ${GIVEN[Math.floor(i / 10)]}`,
      studentCode: code,
      email: `sv${code}@sis.edu.vn`,
      skill: SKILLS[i % SKILLS.length],
    };
  },
);

/**
 * 19 teams: 17 of five and 2 of four (93 students). The other 7 have no team;
 * two of them have asked to join one.
 */
const TEAM_SIZES = [...Array.from({ length: 17 }, () => 5), 4, 4];

export interface LargeTeam {
  teamId: string;
  name: string;
  /** Student ids; the first is the leader. */
  memberIds: readonly string[];
}

export const LARGE_TEAMS: readonly LargeTeam[] = (() => {
  let cursor = 0;
  return TEAM_SIZES.map((size, index) => {
    const memberIds = LARGE_STUDENTS.slice(cursor, cursor + size).map((student) => student.userId);
    cursor += size;
    return { teamId: `team-big-${index + 1}`, name: `Team ${TEAM_NAMES[index]}`, memberIds };
  });
})();

/** Students without a team, in roster order. */
export const LARGE_UNTEAMED_IDS: readonly string[] = LARGE_STUDENTS.slice(
  TEAM_SIZES.reduce((total, size) => total + size, 0),
).map((student) => student.userId);

/** `userId:courseId` → pending request, for the first two students without a team. */
export const LARGE_PENDING_REQUESTS: Record<string, { teamId: string }> = {
  [`${LARGE_UNTEAMED_IDS[0]}:${LARGE_COURSE_ID}`]: { teamId: "team-big-18" },
  [`${LARGE_UNTEAMED_IDS[1]}:${LARGE_COURSE_ID}`]: { teamId: "team-big-19" },
};
