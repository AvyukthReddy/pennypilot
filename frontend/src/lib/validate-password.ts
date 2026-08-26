export function validatePasswordInput(
  password: FormDataEntryValue | null,
  confirmPassword: FormDataEntryValue | null,
): string | null {
  if (typeof password !== "string" || password.length < 6) {
    return "Password must be at least 6 characters";
  }
  if (password !== confirmPassword) {
    return "Passwords don't match";
  }
  return null;
}
