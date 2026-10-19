/**
 * Service worker của MSW giữ danh sách client trong bộ nhớ. Trình duyệt có thể
 * chấm dứt worker khi nhàn rỗi; worker khởi động lại với danh sách rỗng nên
 * bypass mọi request cho tới khi trang được tải lại. Gửi lại MOCK_ACTIVATE
 * định kỳ và mỗi khi tab hiện lại để trang này luôn được worker nhận diện.
 */
export const MOCK_ACTIVATE_MESSAGE = "MOCK_ACTIVATE";
export const REACTIVATE_INTERVAL_MS = 5_000;

export function keepMockWorkerActive(): () => void {
  const container = navigator.serviceWorker;
  if (!container) {
    return () => {};
  }
  const reactivate = () => {
    container.controller?.postMessage(MOCK_ACTIVATE_MESSAGE);
  };
  const onVisibilityChange = () => {
    if (document.visibilityState === "visible") {
      reactivate();
    }
  };
  const interval = window.setInterval(reactivate, REACTIVATE_INTERVAL_MS);
  document.addEventListener("visibilitychange", onVisibilityChange);
  container.addEventListener("controllerchange", reactivate);
  reactivate();
  return () => {
    window.clearInterval(interval);
    document.removeEventListener("visibilitychange", onVisibilityChange);
    container.removeEventListener("controllerchange", reactivate);
  };
}
