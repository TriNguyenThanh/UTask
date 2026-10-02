import { isRouteErrorResponse, useRouteError } from "react-router-dom";

import { ErrorState } from "@/components/feedback/ErrorState";

export function RouteError() {
  const error = useRouteError();
  if (isRouteErrorResponse(error) && error.status === 404) {
    return (
      <main className="grid min-h-screen place-items-center p-6">
        <section className="text-center">
          <p className="text-sm font-semibold text-primary">404</p>
          <h1 className="mt-2 text-2xl font-bold">Không tìm thấy trang</h1>
        </section>
      </main>
    );
  }
  return <main className="p-6"><ErrorState error={error} /></main>;
}
