"use server";

import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { getOrigin } from "@/lib/get-origin";
import { createClient } from "@/lib/supabase/server";

export async function signup(formData: FormData) {
  const email = formData.get("email");
  const password = formData.get("password");

  if (typeof email !== "string" || typeof password !== "string") {
    redirect("/signup?error=Email and password are required");
  }

  const origin = await getOrigin();
  const supabase = createClient(await cookies());
  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: { emailRedirectTo: `${origin}/auth/callback?next=/dashboard` },
  });

  if (error) {
    redirect(`/signup?error=${encodeURIComponent(error.message)}`);
  }

  if (data.session) {
    // Project has email auto-confirm enabled — the user is already signed in.
    revalidatePath("/", "layout");
    redirect("/dashboard");
  }

  redirect("/login?message=Check your email to confirm your account");
}
