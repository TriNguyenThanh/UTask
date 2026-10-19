import { LogOut } from "lucide-react";

import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/layout/PageHeader";
import { useSignOut } from "@/features/auth/useSignOut";

export function Component() {
  const signOut = useSignOut();

  return (
    <main id="main-content" className="container py-8">
      <PageHeader
        title="UTask"
        description="Luồng xác thực đã sẵn sàng. Các màn hình kế tiếp sẽ được xây từng slice."
      >
        <Button variant="outline" onClick={() => void signOut()}>
          <LogOut className="mr-2 size-4" aria-hidden />
          Đăng xuất
        </Button>
      </PageHeader>
    </main>
  );
}