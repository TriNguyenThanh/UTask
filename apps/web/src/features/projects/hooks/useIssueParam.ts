import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

/** Dấu đánh dấu panel được mở bằng thao tác trong app (push), để đóng bằng `navigate(-1)` không để lại mục lịch sử thừa. */
interface IssueLocationState {
  issueOpenedInApp?: boolean;
}

/** Trạng thái panel issue nằm trong query `?issue=KEY` của Board/Backlog. */
export function useIssueParam(): {
  issueKey: string | null;
  openIssue: (key: string) => void;
  closeIssue: () => void;
} {
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const issueKey = searchParams.get("issue");

  const openIssue = (key: string) =>
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set("issue", key);
        return next;
      },
      { preventScrollReset: true, replace: issueKey !== null, state: { issueOpenedInApp: true } },
    );

  const closeIssue = () => {
    if ((location.state as IssueLocationState | null)?.issueOpenedInApp === true) {
      navigate(-1);
      return;
    }
    const next = new URLSearchParams(searchParams);
    next.delete("issue");
    setSearchParams(next, { replace: true, preventScrollReset: true });
  };

  return { issueKey, openIssue, closeIssue };
}
