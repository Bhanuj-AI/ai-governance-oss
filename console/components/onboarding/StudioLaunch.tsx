"use client";

import { useState } from "react";
import { HomeDashboard } from "@/components/home/HomeDashboard";
import { OnboardingJourney } from "@/components/onboarding/OnboardingJourney";
import { ONBOARDING_STARTUP_KEY } from "@/lib/onboarding";

export function StudioLaunch() {
  const [showJourney, setShowJourney] = useState(() =>
    typeof window === "undefined" || window.localStorage.getItem(ONBOARDING_STARTUP_KEY) !== "true",
  );

  if (!showJourney) return <HomeDashboard />;

  return <OnboardingJourney onOpenDashboard={() => setShowJourney(false)} />;
}
