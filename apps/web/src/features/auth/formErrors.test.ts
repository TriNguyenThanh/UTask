import { describe, expect, it } from "vitest";
import { renderHook } from "@testing-library/react";
import { useForm } from "react-hook-form";

import { applyFieldErrors } from "@/features/auth/formErrors";
import { ApiError } from "@/lib/api/errors";

describe("applyFieldErrors", () => {
  function setup() {
    return renderHook(() => useForm<{ email: string; password: string }>()).result.current;
  }

  it("maps backend fields onto form fields and reports that it did", () => {
    const form = setup();
    const error = new ApiError({ status: 400, message: "x", fieldErrors: { password1: ["Quá ngắn.", "Quá phổ biến."] } });

    expect(applyFieldErrors(form, error, { password1: "password" })).toBe(true);
    expect(form.getFieldState("password").error?.message).toBe("Quá ngắn. Quá phổ biến.");
  });

  it("returns false and sets nothing when no mapped field has errors", () => {
    const form = setup();
    const error = new ApiError({ status: 400, message: "x", fieldErrors: { other: ["?"] } });

    expect(applyFieldErrors(form, error, { email: "email" })).toBe(false);
    expect(form.getFieldState("email").error).toBeUndefined();
  });
});
