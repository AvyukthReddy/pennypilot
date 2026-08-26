"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { validatePasswordInput } from "@/lib/validate-password";

export async function changePassword(formData: FormData) {
  const password = formData.get("password");
  const confirmPassword = formData.get("confirmPassword");

  const validationError = validatePasswordInput(password, confirmPassword);
  if (validationError) {
    redirect(`/settings?error=${validationError}`);
  }

  const supabase = createClient(await cookies());

  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    redirect("/login");
  }

  // Already validated as a non-empty string by validatePasswordInput above.
  const { error } = await supabase.auth.updateUser({ password: password as string });
  if (error) {
    redirect(`/settings?error=${encodeURIComponent(error.message)}`);
  }

  redirect("/settings?message=Password updated");
}
