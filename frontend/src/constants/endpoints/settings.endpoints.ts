import { getApiUrl } from "@/services/app.service";

export const settingsEndpoints = {
  profile: () => getApiUrl("/api/profile"),
};
