import { createContext, useContext, useEffect } from "react";

/** AuthenticatedLayout cung cấp setter; route có tiêu đề động gọi usePageTitle. */
export const PageTitleContext = createContext<(title: string | null) => void>(() => {});

export function usePageTitle(title: string | null) {
  const setTitle = useContext(PageTitleContext);
  useEffect(() => {
    setTitle(title);
    return () => setTitle(null);
  }, [setTitle, title]);
}
