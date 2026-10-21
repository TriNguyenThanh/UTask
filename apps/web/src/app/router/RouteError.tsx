import { isRouteErrorResponse, Link, useRouteError } from "react-router-dom";

import { ErrorState } from "@/components/feedback/ErrorState";
import { Button } from "@/components/ui/button";

export function RouteError({ inShell = false }: Readonly<{ inShell?: boolean }>) {
  const error = useRouteError();
  const Wrapper = inShell ? "section" : "main";
  if (isRouteErrorResponse(error) && error.status === 404) {
    return (
      <Wrapper className="grid min-h-screen place-items-center p-6">
        <div className="text-center">
          <p className="text-sm font-semibold text-primary">404</p>
          <h1 className="mt-2 text-2xl font-bold">Không tìm thấy trang</h1>
          <Button className="mt-6" asChild><Link to="/">Về trang chủ</Link></Button>
        </div>
      </Wrapper>
    );
  }
  return (
    <Wrapper className="space-y-4 p-6">
      <h1 className="text-2xl font-bold">Không mở được trang này</h1>
      <ErrorState error={error} onRetry={() => window.location.reload()} />
      <Button variant="outline" asChild><Link to="/">Về trang chủ</Link></Button>
    </Wrapper>
  );
}
