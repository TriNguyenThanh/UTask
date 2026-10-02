import { useEffect, useState } from "react";
import { toast } from "sonner";
import { BadgeCheck, Info, Lock, Save } from "lucide-react";

import { ErrorState } from "@/components/feedback/ErrorState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { SettingsHeader } from "@/features/notifications/components/SettingsHeader";
import type { AccountSettings } from "@/features/notifications/types";
import { useAccountSettings, useUpdateAccountSettings } from "@/lib/query/studentFlowHooks";

interface ProfileForm {
  fullName: string;
  cohortClass: string;
  faculty: string;
  phone: string;
}

function formFromSettings(settings: AccountSettings): ProfileForm {
  return {
    fullName: settings.fullName,
    cohortClass: settings.cohortClass,
    faculty: settings.faculty,
    phone: settings.phone,
  };
}

/** Initials for avatar fallback, e.g. "Nguyễn Hoàng Nam" → "HN". */
function initialsOf(fullName: string): string {
  const words = fullName.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}

function ProfileSkeleton() {
  return (
    <div className="space-y-6" role="status" aria-label="Đang tải cài đặt hồ sơ">
      <Skeleton className="h-8 w-80" />
      <div className="flex items-center gap-5 py-4">
        <Skeleton className="size-16 rounded-full" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-8 w-44" />
          <Skeleton className="h-4 w-72" />
        </div>
      </div>
      <div className="grid gap-6 md:grid-cols-2">
        {Array.from({ length: 6 }, (_, index) => (
          <div key={index} className="space-y-2">
            <Skeleton className="h-4 w-28" />
            <Skeleton className="h-9 w-full" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function SettingsProfilePage() {
  const settingsQuery = useAccountSettings();
  const updateSettings = useUpdateAccountSettings();

  const settings = settingsQuery.data;
  const [form, setForm] = useState<ProfileForm | null>(null);

  // Re-seed local form state whenever fresh settings land (initial load, refetch).
  useEffect(() => {
    if (settings) {
      setForm(formFromSettings(settings));
    }
  }, [settings]);

  const dirty =
    settings !== undefined &&
    form !== null &&
    (form.fullName !== settings.fullName ||
      form.cohortClass !== settings.cohortClass ||
      form.faculty !== settings.faculty ||
      form.phone !== settings.phone);

  function setField(field: keyof ProfileForm, value: string) {
    setForm((current) => (current === null ? current : { ...current, [field]: value }));
  }

  function handleReset() {
    if (settings) {
      setForm(formFromSettings(settings));
    }
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!form || !dirty) return;
    updateSettings.mutate(
      {
        fullName: form.fullName.trim(),
        cohortClass: form.cohortClass.trim(),
        faculty: form.faculty.trim(),
        phone: form.phone.trim(),
      },
      {
        onSuccess: () => toast.success("Đã lưu thông tin hồ sơ"),
        onError: () => toast.error("Không thể lưu hồ sơ. Vui lòng thử lại."),
      },
    );
  }

  if (settingsQuery.isError) {
    return (
      <div className="mx-auto max-w-6xl space-y-6 px-4 pt-7 sm:px-6 lg:px-8">
        <SettingsHeader />
        <ErrorState error={settingsQuery.error} onRetry={() => settingsQuery.refetch()} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-8 px-4 pt-7 sm:px-6 lg:px-8">
      <SettingsHeader />

      {settingsQuery.isPending || !settings || !form ? (
        <ProfileSkeleton />
      ) : (
        <section aria-labelledby="profile-section-title" className="space-y-6">
          <header className="space-y-1">
            <h2 id="profile-section-title" className="text-lg font-semibold">
              Thông tin Học vụ Sinh viên
            </h2>
            <p className="text-sm text-muted-foreground">
              Dữ liệu chính quy được đồng bộ từ Cơ sở Dữ liệu Sinh viên ĐHQG TP.HCM.
            </p>
          </header>

          <div className="flex flex-col items-start gap-5 border-y py-4 sm:flex-row sm:items-center">
            <div
              className="flex size-16 shrink-0 items-center justify-center rounded-full bg-secondary text-xl font-bold text-primary"
              aria-hidden
            >
              {initialsOf(form.fullName || settings.fullName)}
            </div>
            <p className="flex-1 text-sm text-muted-foreground">
              Ảnh đại diện sử dụng chữ cái đầu họ và tên. Tải ảnh sẽ khả dụng khi backend hỗ trợ.
            </p>
          </div>

          <form className="grid grid-cols-1 gap-x-8 gap-y-6 md:grid-cols-2" onSubmit={handleSubmit}>
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label className="flex items-center gap-1.5">
                  Mã số sinh viên (MSSV)
                  <Lock className="size-3.5 text-muted-foreground" aria-hidden />
                </Label>
                <Badge variant="outline" className="gap-1 border-emerald-200 bg-emerald-50 text-emerald-800">
                  <BadgeCheck className="size-3 text-emerald-600" aria-hidden />
                  Đã xác thực
                </Badge>
              </div>
              <Input value={settings.studentId} readOnly className="cursor-not-allowed font-mono" />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="profile-full-name">Họ và tên đầy đủ</Label>
              <Input
                id="profile-full-name"
                value={form.fullName}
                onChange={(event) => setField("fullName", event.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label className="flex items-center gap-1.5">
                  Email trường học
                  <Lock className="size-3.5 text-muted-foreground" aria-hidden />
                </Label>
                <span className="text-xs text-muted-foreground">Chỉ đọc</span>
              </div>
              <Input type="email" value={settings.email} readOnly className="cursor-not-allowed" />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="profile-cohort-class">Lớp sinh hoạt / Chuyên ngành</Label>
              <Input
                id="profile-cohort-class"
                value={form.cohortClass}
                onChange={(event) => setField("cohortClass", event.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="profile-faculty">Khoa / Viện quản lý trực tiếp</Label>
              <Input
                id="profile-faculty"
                value={form.faculty}
                onChange={(event) => setField("faculty", event.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="profile-phone">Số điện thoại liên hệ (Khẩn cấp)</Label>
              <Input
                id="profile-phone"
                type="tel"
                value={form.phone}
                onChange={(event) => setField("phone", event.target.value)}
              />
            </div>

            <div className="flex flex-col justify-between gap-4 border-t pt-4 md:col-span-2 md:flex-row md:items-center">
              <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
                <Info className="size-4" aria-hidden />
                Lần cập nhật gần nhất:{" "}
                {new Date(settings.updatedAt).toLocaleString("vi-VN")}
              </span>
              <div className="flex items-center gap-3">
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleReset}
                  disabled={!dirty}
                >
                  Hủy thay đổi
                </Button>
                <Button type="submit" disabled={!dirty || updateSettings.isPending}>
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