import { redirect } from "next/navigation";

// Password reset now uses a one-time code entered on /forgot-password; keep old links working.
export default function ResetPasswordPage() {
  redirect("/forgot-password");
}
