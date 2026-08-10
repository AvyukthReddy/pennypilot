"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { getOrigin } from "@/lib/get-origin";
import { createClient } from "@/lib/supabase/server";

export async function requestPasswordReset(formData: FormData) {
  const email = formData.get("email");

  if (typeof email !== "string" || email.length === 0) {
    redirect("/forgot-password?error=Enter your email address");
  }

  const origin = await getOrigin();
  const supabase = createClient(await cookies());
  const { error } = await supabase.auth.resetPasswordForEmail(email, {
    redirectTo: `${origin}/auth/callback?next=/reset-password`,
  });

  if (error) {
    redirect(`/forgot-password?error=${encodeURIComponent(error.message)}`);
  }

  redirect("/forgot-password?message=If an account exists for that email, a reset link is on its way");
}
