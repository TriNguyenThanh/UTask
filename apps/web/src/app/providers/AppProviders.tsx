import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";

import { appRouter } from "@/app/router/router";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/features/auth/AuthProvider";
import { ApiClientProvider } from "@/lib/api/ApiClientProvider";
import { createQueryClient } from "@/lib/query/client";

const queryClient = createQueryClient();

export function AppProviders() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ApiClientProvider>
          <TooltipProvider>
            <RouterProvider router={appRouter} />
            <Toaster richColors position="top-right" />
          </TooltipProvider>
        </ApiClientProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
