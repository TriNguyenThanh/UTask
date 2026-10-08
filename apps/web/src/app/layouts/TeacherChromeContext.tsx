import { createContext, useContext } from "react";

/**
 * Lets a shared page (the project workspace) ask the shell for the Teacher
 * navigation when the viewer is an instructor. The shell cannot know this on
 * its own: the same URL serves team members and instructors.
 */
export const TeacherChromeContext = createContext<(instructorView: boolean) => void>(() => {});

export function useRequestTeacherChrome(): (instructorView: boolean) => void {
  return useContext(TeacherChromeContext);
}
