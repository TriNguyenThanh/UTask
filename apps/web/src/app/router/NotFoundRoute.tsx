import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";

export function Component() {
  return (
    <main className="grid min-h-screen place-items-center p-6">
      <section className="text-center">
        <p className="text-sm font-semibold text-primary">404</p>
        <h1 className="mt-2 text-3xl font-bold">Không tìm thấy trang</h1>
        <p className="mt-3 text-muted-foreground">Đường dẫn này không tồn tại hoặc đã được thay đổi.</p>
        <Button className="mt-6" asChild><Link to="/">Về trang chủ</Link></Button>
      </section>
    </main>
  );
}
