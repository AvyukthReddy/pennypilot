"use client";

import { useState } from "react";

import { APP_METHOD } from "@/constants/app.constants";
import { statementsEndpoints } from "@/constants/endpoints/statements.endpoints";
import { useApiRequest } from "@/hooks/use-api-request";

export function useSignedUrlView() {
  const [viewingId, setViewingId] = useState<string | null>(null);
  const viewRequest = useApiRequest<{ url: string }>();

  async function view(id: string) {
    setViewingId(id);
    // Open the tab synchronously on click so browsers don't treat the later
    // redirect (after the signed-URL request resolves) as a blocked popup.
    // Can't pass noopener/noreferrer here, those make window.open() return
    // null, which would leave us with no handle to redirect later.
    const viewerTab = window.open("", "_blank");

    const data = await viewRequest.run(statementsEndpoints.view(id), APP_METHOD.GET);
    setViewingId(null);

    if (data?.url && viewerTab) {
      viewerTab.opener = null;
      viewerTab.location.href = data.url;
    } else {
      viewerTab?.close();
    }
  }

  return { viewingId, view, error: viewRequest.error };
}
