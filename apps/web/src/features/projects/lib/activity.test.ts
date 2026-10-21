import { describe, expect, it } from "vitest";

import { describeActivity, formatActivityValue, parseActivityValue } from "@/features/projects/lib/activity";

describe("parseActivityValue", () => {
  it("parses serialized JSON, keeps plain text and null as they are", () => {
    expect(parseActivityValue('["a","b"]')).toEqual(["a", "b"]);
    expect(parseActivityValue('"Đang làm"')).toBe("Đang làm");
    expect(parseActivityValue("5")).toBe(5);
    expect(parseActivityValue("Đang làm")).toBe("Đang làm");
    expect(parseActivityValue("{không phải json")).toBe("{không phải json");
    expect(parseActivityValue(null)).toBeNull();
  });
});

describe("formatActivityValue", () => {
  it("shows empty values as (trống), joins lists and truncates long text", () => {
    expect(formatActivityValue(null)).toBe("(trống)");
    expect(formatActivityValue("")).toBe("(trống)");
    expect(formatActivityValue([])).toBe("(trống)");
    expect(formatActivityValue(["x", 2, true])).toBe("x, 2, true");
    expect(formatActivityValue({ a: 1 })).toBe('{"a":1}');
    const long = formatActivityValue("a".repeat(200));
    expect(long).toHaveLength(80);
    expect(long.endsWith("…")).toBe(true);
  });
});

describe("describeActivity", () => {
  it("describes a field change with a Vietnamese field name and both values", () => {
    expect(describeActivity({ verb: "updated", field: "priority", old_value: '"LOW"', new_value: '"HIGH"' })).toBe(
      "đã đổi độ ưu tiên: LOW → HIGH",
    );
    expect(describeActivity({ verb: "updated", field: "story_points", old_value: null, new_value: "5" })).toBe(
      "đã đổi điểm: (trống) → 5",
    );
  });

  it("keeps an unknown field name and falls back when nothing changed", () => {
    expect(describeActivity({ verb: "updated", field: "custom", old_value: "1", new_value: "2" })).toBe("đã đổi custom: 1 → 2");
    expect(describeActivity({ verb: "updated", field: null, old_value: null, new_value: null })).toBe("đã cập nhật dữ liệu");
  });

  it("maps known verbs and passes an unknown verb through unchanged", () => {
    expect(describeActivity({ verb: "created", field: null, old_value: null, new_value: null })).toBe("đã tạo");
    expect(describeActivity({ verb: "restored", field: null, old_value: null, new_value: null })).toBe("đã khôi phục");
    expect(describeActivity({ verb: "commented", field: null, old_value: null, new_value: null })).toBe("commented");
  });
});
