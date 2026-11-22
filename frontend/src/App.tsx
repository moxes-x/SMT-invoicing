import { createBrowserRouter, Navigate, Outlet, RouterProvider } from "react-router";

import { useMe } from "@/api/auth";
import { AppLayout } from "@/components/app-layout";
import { CustomersPage } from "@/pages/customers";
import { DashboardPage } from "@/pages/dashboard";
import { InvoiceDetailPage } from "@/pages/invoice-detail";
import { InvoiceEditorPage } from "@/pages/invoice-editor";
import { InvoicesPage } from "@/pages/invoices";
import { ItemsPage } from "@/pages/items";
import { LoginPage } from "@/pages/login";
import { MorePage } from "@/pages/more";
import { OnboardingPage } from "@/pages/onboarding";
import { QuoteDetailPage } from "@/pages/quote-detail";
import { QuoteEditorPage } from "@/pages/quote-editor";
import { QuotesPage } from "@/pages/quotes";
import { RecurringPage } from "@/pages/recurring";
import { RecurringEditorPage } from "@/pages/recurring-editor";
import { SettingsPage } from "@/pages/settings";
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
    children: [
      {
        element: <AppLayout />,
        children: [
          { path: "/", element: <DashboardPage /> },
          { path: "/invoices", element: <InvoicesPage /> },
          { path: "/invoices/new", element: <InvoiceEditorPage /> },
          { path: "/invoices/:id", element: <InvoiceDetailPage /> },
          { path: "/invoices/:id/edit", element: <InvoiceEditorPage /> },
          { path: "/quotes", element: <QuotesPage /> },
          { path: "/quotes/new", element: <QuoteEditorPage /> },
          { path: "/quotes/:id", element: <QuoteDetailPage /> },
          { path: "/quotes/:id/edit", element: <QuoteEditorPage /> },
          { path: "/recurring", element: <RecurringPage /> },
          { path: "/recurring/new", element: <RecurringEditorPage /> },
          { path: "/recurring/:id/edit", element: <RecurringEditorPage /> },
          { path: "/customers", element: <CustomersPage /> },
          { path: "/items", element: <ItemsPage /> },
          { path: "/settings", element: <SettingsPage /> },
          { path: "/more", element: <MorePage /> },
        ],
      },
    ],
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
