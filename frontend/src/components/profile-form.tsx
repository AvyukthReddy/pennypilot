"use client";

import { useEffect, useRef, useState, type ChangeEvent, type SubmitEvent } from "react";

import { APP_METHOD } from "@/constants/app.constants";
import { settingsEndpoints } from "@/constants/endpoints/settings.endpoints";
import { useApiRequest } from "@/hooks/use-api-request";
import { compressImage } from "@/lib/compress-image";
import { COUNTRIES } from "@/lib/countries";
import { ProfileFormSkeleton } from "@/components/skeleton";

const CURRENCIES = Array.from(new Set(COUNTRIES.map((c) => c.currency))).sort((a, b) =>
  a.localeCompare(b),
);

const ACCEPTED_IMAGE_TYPES = "image/jpeg,image/png,image/webp";
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

type Profile = {
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  country: string | null;
  currency: string | null;
  profile_image: string | null;
};

const EMPTY_PROFILE: Profile = {
  username: null,
  first_name: null,
  last_name: null,
  country: null,
  currency: null,
  profile_image: null,
};

function initials(profile: Profile): string {
  const first = profile.first_name?.[0] ?? profile.username?.[0] ?? "";
  const last = profile.last_name?.[0] ?? "";
  return (first + last).toUpperCase() || "?";
}

export function ProfileForm() {
  const [profile, setProfile] = useState<Profile>(EMPTY_PROFILE);
  const [saved, setSaved] = useState(false);
  const [imageError, setImageError] = useState<string | null>(null);
  const profileRequest = useApiRequest<Profile>();
  const saveRequest = useApiRequest<Profile>();
  const imageRequest = useApiRequest<Profile>();
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    profileRequest.run(settingsEndpoints.profile(), APP_METHOD.GET).then((data) => {
      if (data) setProfile(data);
    });
    // profileRequest.run is stable (useCallback with no deps) — safe to omit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaved(false);

    const data = await saveRequest.run(
      settingsEndpoints.profile(),
      APP_METHOD.PUT,
      JSON.stringify(profile),
    );

    if (data) {
      setProfile(data);
      setSaved(true);
    }
  }

  async function handleImageChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    setImageError(null);

    const upload = file.size > MAX_IMAGE_BYTES ? await compressImage(file, MAX_IMAGE_BYTES) : file;

    if (upload.size > MAX_IMAGE_BYTES) {
      setImageError("Image is too large even after compression — try a smaller photo");
      return;
    }

    const formData = new FormData();
    formData.append("file", upload);

    const data = await imageRequest.run(settingsEndpoints.profileImage(), APP_METHOD.POST, formData);
    if (data) setProfile(data);
  }

  function handleCountryChange(code: string) {
    const country = COUNTRIES.find((c) => c.code === code);
    setProfile((prev) => ({
      ...prev,
      country: code || null,
      currency: country ? country.currency : prev.currency,
    }));
  }

  if (!profileRequest.hasSettled) {
    return <ProfileFormSkeleton />;
  }

  if (profileRequest.error) {
    return (
      <p className="text-sm text-red-600 dark:text-red-400" aria-live="polite">
        {profileRequest.error}
      </p>
    );
  }

  const inputClass =
    "rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-black outline-none focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-50";

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={imageRequest.loading}
          aria-label="Change profile photo"
          className="relative flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-full border border-zinc-300 bg-zinc-100 text-lg font-semibold text-zinc-600 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
        >
          {profile.profile_image ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={profile.profile_image}
              alt="Profile"
              className="h-full w-full object-cover"
            />
          ) : (
            initials(profile)
          )}
          {imageRequest.loading && (
            <span className="absolute inset-0 flex items-center justify-center bg-black/40 text-xs text-white">
              …
            </span>
          )}
        </button>

        <div className="flex flex-col gap-1">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={imageRequest.loading}
            className="self-start text-sm font-medium text-black underline disabled:opacity-50 dark:text-zinc-50"
          >
            {imageRequest.loading ? "Uploading…" : "Change photo"}
          </button>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            JPEG, PNG, or WebP — large images are compressed automatically.
          </p>
          {(imageError || imageRequest.error) && (
            <p className="text-xs text-red-600 dark:text-red-400" aria-live="polite">
              {imageError || imageRequest.error}
            </p>
          )}
        </div>

        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_IMAGE_TYPES}
          onChange={handleImageChange}
          className="hidden"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="username" className="text-sm text-zinc-600 dark:text-zinc-400">
          Username
        </label>
        <input
          id="username"
          value={profile.username ?? ""}
          onChange={(e) => setProfile((prev) => ({ ...prev, username: e.target.value || null }))}
          minLength={3}
          maxLength={50}
          className={inputClass}
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="flex flex-col gap-1">
          <label htmlFor="first_name" className="text-sm text-zinc-600 dark:text-zinc-400">
            First name
          </label>
          <input
            id="first_name"
            value={profile.first_name ?? ""}
            onChange={(e) =>
              setProfile((prev) => ({ ...prev, first_name: e.target.value || null }))
            }
            maxLength={100}
            className={inputClass}
          />
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="last_name" className="text-sm text-zinc-600 dark:text-zinc-400">
            Last name
          </label>
          <input
            id="last_name"
            value={profile.last_name ?? ""}
            onChange={(e) => setProfile((prev) => ({ ...prev, last_name: e.target.value || null }))}
            maxLength={100}
            className={inputClass}
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="flex flex-col gap-1">
          <label htmlFor="country" className="text-sm text-zinc-600 dark:text-zinc-400">
            Country
          </label>
          <select
            id="country"
            value={profile.country ?? ""}
            onChange={(e) => handleCountryChange(e.target.value)}
            className={inputClass}
          >
            <option value="">Select a country</option>
            {COUNTRIES.map((c) => (
              <option key={c.code} value={c.code}>
                {c.name}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="currency" className="text-sm text-zinc-600 dark:text-zinc-400">
            Currency
          </label>
          <select
            id="currency"
            value={profile.currency ?? ""}
            onChange={(e) => setProfile((prev) => ({ ...prev, currency: e.target.value || null }))}
            className={inputClass}
          >
            <option value="">Select a currency</option>
            {CURRENCIES.map((currency) => (
              <option key={currency} value={currency}>
                {currency}
              </option>
            ))}
          </select>
        </div>
      </div>

      {saveRequest.error && (
        <p className="text-sm text-red-600 dark:text-red-400" aria-live="polite">
          {saveRequest.error}
        </p>
      )}
      {saved && !saveRequest.error && (
        <p className="text-sm text-emerald-600 dark:text-emerald-400" aria-live="polite">
          Profile updated
        </p>
      )}

      <button
        type="submit"
        disabled={saveRequest.loading}
        className="mt-2 self-start rounded-md bg-black px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50 dark:bg-zinc-50 dark:text-black dark:hover:bg-zinc-200"
      >
        {saveRequest.loading ? "Saving…" : "Save profile"}
      </button>
    </form>
  );
}
