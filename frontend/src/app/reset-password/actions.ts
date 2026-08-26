"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { validatePasswordInput } from "@/lib/validate-password";

export async function updatePassword(formData: FormData) {
  const password = formData.get("password");
  const confirmPassword = formData.get("confirmPassword");

  const validationError = validatePasswordInput(password, confirmPassword);
  if (validationError) {
    redirect(`/reset-password?error=${validationError}`);
  }

  const supabase = createClient(await cookies());

  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    redirect("/forgot-password?error=Your reset link has expired, request a new one");
  }

  // Already validated as a non-empty string by validatePasswordInput above.
  const { error } = await supabase.auth.updateUser({ password: password as string });
  if (error) {
    redirect(`/reset-password?error=${encodeURIComponent(error.message)}`);
  }

  redirect("/dashboard");
}
