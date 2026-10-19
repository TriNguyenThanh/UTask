import { useEffect, useState } from "react";
import { toast } from "sonner";
import { BadgeCheck, Lock, Save } from "lucide-react";

import { ErrorState } from "@/components/feedback/ErrorState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { FieldError } from "@/features/notifications/components/FieldError";
import { SettingsHeader } from "@/features/notifications/components/SettingsHeader";
import { initialsOf, ProfileSkeleton } from "@/features/notifications/components/SettingsProfilePage";
import { ApiError } from "@/lib/api/errors";
import type { CurrentUserDto, ProfilePatchDto } from "@/lib/api/identity/dto";
import { useMe, usePatchMe } from "@/lib/query/identityHooks";

interface ProfileForm {
  last_name: string;
  first_name: string;
  phone_number: string;
  academic_year: string;
  faculty: string;
  bio: string;
  timezone: string;
}

const FIELDS = [
  "last_name",
  "first_name",
  "phone_number",
  "academic_year",
  "faculty",
  "bio",
  "timezone",
] as const satisfies readonly (keyof ProfileForm)[];

export function formFromUser(user: CurrentUserDto): ProfileForm {
  return {
    last_name: user.last_name,
    first_name: user.first_name,
    phone_number: user.phone_number ?? "",
    academic_year: user.academic_year ?? "",
    faculty: user.faculty ?? "",
    bio: user.bio ?? "",
    timezone: user.timezone,
  };
}

/** Chỉ gửi trường đã đổi; trường tùy chọn để trống gửi `null` để xóa giá trị. */
export function buildPatch(user: CurrentUserDto, form: ProfileForm): ProfilePatchDto {
  const original = formFromUser(user);
  const patch: ProfilePatchDto = {};
  for (const field of FIELDS) {
    const value = form[field].trim();
    if (value === original[field]) {
      continue;
    }
    const nullable = field === "phone_number" || field === "academic_year" || field === "faculty" || field === "bio";
    Object.assign(patch, { [field]: nullable && value === "" ? null : value });
  }
  return patch;
}

export function IdentityProfilePage() {
  const meQuery = useMe();
  const patchMe = usePatchMe();
  const user = meQuery.data;
  const [form, setForm] = useState<ProfileForm | null>(null);

  // Nạp lại form mỗi khi máy chủ trả hồ sơ mới (lần đầu, sau khi lưu).
  useEffect(() => {
    if (user) {
      setForm(formFromUser(user));
    }
  }, [user]);

  const patch = user && form ? buildPatch(user, form) : {};
  const dirty = Object.keys(patch).length > 0;
  const fieldErrors = patchMe.error instanceof ApiError ? patchMe.error.fieldErrors : {};

  function setField(field: keyof ProfileForm, value: string) {
    setForm((current) => (current === null ? current : { ...current, [field]: value }));
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!dirty) {
      return;
    }
    patchMe.mutate(patch, {
      onSuccess: () => toast.success("Đã lưu thông tin hồ sơ"),
      onError: (error) => {
        // Lỗi theo trường đã hiện ngay dưới ô nhập; chỉ báo thêm khi không có trường nào.
        if (!(error instanceof ApiError) || Object.keys(error.fieldErrors).length === 0) {
          toast.error(error.message || "Không thể lưu hồ sơ. Vui lòng thử lại.");
        }
      },
    });
  }

  if (meQuery.isError) {
    return (
      <div className="page-container space-y-6 px-4 pt-7 short:pt-4 sm:px-6 lg:px-8">
        <SettingsHeader />
        <ErrorState error={meQuery.error} onRetry={() => meQuery.refetch()} />
      </div>
    );
  }

  return (
    <div className="page-container space-y-8 short:space-y-4 px-4 pt-7 short:pt-4 sm:px-6 lg:px-8">
      <SettingsHeader />

      {meQuery.isPending || !user || !form ? (
        <ProfileSkeleton />
      ) : (
        <section aria-labelledby="profile-section-title" className="space-y-6 short:space-y-3">
          <header className="space-y-1">
            <h2 id="profile-section-title" className="text-lg font-semibold">
              Thông tin tài khoản
            </h2>
            <p className="text-sm text-muted-foreground">
              Email, tên đăng nhập và MSSV do hệ thống quản lý nên chỉ đọc.
            </p>
          </header>

          <div className="flex flex-col items-start gap-5 border-y py-4 short:py-2 sm:flex-row sm:items-center">
            <div
              className="flex size-16 short:size-10 shrink-0 items-center justify-center rounded-full bg-secondary text-xl font-bold text-primary"
              aria-hidden
            >
              {initialsOf(user.display_name || `${user.last_name} ${user.first_name}`)}
            </div>
            <p className="flex-1 text-sm text-muted-foreground">
              Ảnh đại diện sử dụng chữ cái đầu họ và tên. Tải ảnh sẽ khả dụng khi backend hỗ trợ.
            </p>
          </div>

          <form className="grid grid-cols-1 gap-x-8 gap-y-6 short:gap-y-3 md:grid-cols-2" onSubmit={handleSubmit}>
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label htmlFor="profile-student-id" className="flex items-center gap-1.5">
                  Mã số sinh viên (MSSV)
                  <Lock className="size-3.5 text-muted-foreground" aria-hidden />
                </Label>
                {user.student_id ? (
                  <Badge variant="outline" className="gap-1 border-emerald-200 bg-emerald-50 text-emerald-800">
                    <BadgeCheck className="size-3 text-emerald-600" aria-hidden />
                    Đã xác thực
                  </Badge>
                ) : null}
              </div>
              <Input
                id="profile-student-id"
                value={user.student_id ?? ""}
                placeholder="Chưa có MSSV"
                readOnly
                className="cursor-not-allowed font-mono"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="profile-email" className="flex items-center gap-1.5">
                Email
                <Lock className="size-3.5 text-muted-foreground" aria-hidden />
              </Label>
              <Input id="profile-email" type="email" value={user.email} readOnly className="cursor-not-allowed" />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="profile-username" className="flex items-center gap-1.5">
                Tên đăng nhập
                <Lock className="size-3.5 text-muted-foreground" aria-hidden />
              </Label>
              <Input id="profile-username" value={user.username} readOnly className="cursor-not-allowed" />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="profile-last-name">Họ và tên đệm</Label>
              <Input
                id="profile-last-name"
                value={form.last_name}
                onChange={(event) => setField("last_name", event.target.value)}
                aria-invalid={fieldErrors.last_name ? true : undefined}
              />
              <FieldError messages={fieldErrors.last_name} />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="profile-first-name">Tên</Label>
              <Input
                id="profile-first-name"
                value={form.first_name}
                onChange={(event) => setField("first_name", event.target.value)}
                aria-invalid={fieldErrors.first_name ? true : undefined}
              />
              <FieldError messages={fieldErrors.first_name} />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="profile-phone">Số điện thoại</Label>
              <Input
                id="profile-phone"
                type="tel"
                value={form.phone_number}
                onChange={(event) => setField("phone_number", event.target.value)}
                aria-invalid={fieldErrors.phone_number ? true : undefined}
              />
              <FieldError messages={fieldErrors.phone_number} />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="profile-academic-year">Khóa</Label>
              <Input
                id="profile-academic-year"
                value={form.academic_year}
                onChange={(event) => setField("academic_year", event.target.value)}
                aria-invalid={fieldErrors.academic_year ? true : undefined}
              />
              <FieldError messages={fieldErrors.academic_year} />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="profile-faculty">Khoa / Viện</Label>
              <Input
                id="profile-faculty"
                value={form.faculty}
                onChange={(event) => setField("faculty", event.target.value)}
                aria-invalid={fieldErrors.faculty ? true : undefined}
              />
              <FieldError messages={fieldErrors.faculty} />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="profile-timezone">Múi giờ</Label>
              <Input
                id="profile-timezone"
                value={form.timezone}
                onChange={(event) => setField("timezone", event.target.value)}
                aria-invalid={fieldErrors.timezone ? true : undefined}
              />
              <FieldError messages={fieldErrors.timezone} />
            </div>

            <div className="space-y-1.5 md:col-span-2">
              <Label htmlFor="profile-bio">Giới thiệu</Label>
              <Textarea
                id="profile-bio"
                value={form.bio}
                onChange={(event) => setField("bio", event.target.value)}
                aria-invalid={fieldErrors.bio ? true : undefined}
              />
              <FieldError messages={fieldErrors.bio} />
            </div>

            <div className="flex flex-col justify-end gap-4 border-t pt-4 md:col-span-2 md:flex-row md:items-center">
              <div className="flex items-center gap-3">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setForm(formFromUser(user))}
                  disabled={!dirty}
                >
                  Hủy thay đổi
                </Button>
                <Button type="submit" disabled={!dirty || patchMe.isPending}>
                  <Save className="size-4" aria-hidden />
                  Lưu thông tin hồ sơ
                </Button>
              </div>
            </div>
          </form>
        </section>
      )}
    </div>
  );
}
