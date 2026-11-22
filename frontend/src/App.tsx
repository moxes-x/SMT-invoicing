import { createBrowserRouter, Navigate, Outlet, RouterProvider } from "react-router";

import { useMe } from "@/api/auth";
import { HomePage } from "@/pages/home";
import { LoginPage } from "@/pages/login";
import { OnboardingPage } from "@/pages/onboarding";
import { SignupPage } from "@/pages/signup";
import { Providers } from "@/providers";

function FullPageSpinner() {
  return (
    <div className="text-muted-foreground flex min-h-svh items-center justify-center text-sm">
      Loading…
    </div>
  );
}

/** Logged-in users only. Users without a business are sent to onboarding. */
function RequireAuth({ needsBusiness = true }: { needsBusiness?: boolean }) {
  const { data: me, isLoading } = useMe();
  if (isLoading) return <FullPageSpinner />;
  if (!me) return <Navigate to="/login" replace />;
  if (needsBusiness && !me.current_business) return <Navigate to="/onboarding" replace />;
  return <Outlet />;
}

function GuestOnly() {
  const { data: me, isLoading } = useMe();
  if (isLoading) return <FullPageSpinner />;
  if (me) return <Navigate to="/" replace />;
  return <Outlet />;
}

const routes = [
  {
    element: <GuestOnly />,
    children: [
      { path: "/login", element: <LoginPage /> },
      { path: "/signup", element: <SignupPage /> },
    ],
  },
  {
    element: <RequireAuth needsBusiness={false} />,
    children: [{ path: "/onboarding", element: <OnboardingPage /> }],
  },
  {
    element: <RequireAuth />,
    children: [{ path: "/", element: <HomePage /> }],
  },
  { path: "*", element: <Navigate to="/" replace /> },
];

const router = createBrowserRouter(routes);

export default function App() {
  return (
    <Providers>
      <RouterProvider router={router} />
    </Providers>
  );
}
