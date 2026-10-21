/** Lỗi theo trường từ `ApiError.fieldErrors`; không hiển thị gì khi không có lỗi. */
export function FieldError({ messages }: { messages: string[] | undefined }) {
  if (!messages?.length) {
    return null;
  }
  return (
    <p className="text-xs text-destructive" role="alert">
      {messages.join(" ")}
    </p>
  );
}
