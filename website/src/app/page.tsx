import { Suspense } from "react";
import { AuthGate } from "@/components/AuthGate";
import { Dashboard } from "@/components/Dashboard";

export default function Page() {
  return (
    <AuthGate>
      <Suspense>
        <Dashboard />
      </Suspense>
    </AuthGate>
  );
}
