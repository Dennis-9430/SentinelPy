import { lazy, Suspense } from "react"
import { createBrowserRouter, Navigate } from "react-router-dom"
import { ProtectedRoute } from "./components/ProtectedRoute"
import { Layout } from "./components/Layout"

const LoginPage = lazy(() => import("./pages/LoginPage"))
const DashboardPage = lazy(() => import("./pages/DashboardPage"))
const EventsPage = lazy(() => import("./pages/EventsPage"))
const AlertsPage = lazy(() => import("./pages/AlertsPage"))
const RulesPage = lazy(() => import("./pages/RulesPage"))
const UsersPage = lazy(() => import("./pages/UsersPage"))
const AgentsPage = lazy(() => import("./pages/AgentsPage"))
const ThreatIntelPage = lazy(() => import("./pages/ThreatIntelPage"))

function LazyFallback() {
  return (
    <div className="flex h-full items-center justify-center p-8">
      <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
    </div>
  )
}

export const router = createBrowserRouter([
  {
    path: "/login",
    element: (
      <Suspense fallback={<LazyFallback />}>
        <LoginPage />
      </Suspense>
    ),
  },
  {
    path: "/",
    element: (
      <ProtectedRoute>
        <Layout />
      </ProtectedRoute>
    ),
    children: [
      {
        index: true,
        element: (
          <Suspense fallback={<LazyFallback />}>
            <DashboardPage />
          </Suspense>
        ),
      },
      {
        path: "events",
        element: (
          <Suspense fallback={<LazyFallback />}>
            <EventsPage />
          </Suspense>
        ),
      },
      {
        path: "alerts",
        element: (
          <Suspense fallback={<LazyFallback />}>
            <AlertsPage />
          </Suspense>
        ),
      },
      {
        path: "rules",
        element: (
          <Suspense fallback={<LazyFallback />}>
            <RulesPage />
          </Suspense>
        ),
      },
      {
        path: "users",
        element: (
          <Suspense fallback={<LazyFallback />}>
            <UsersPage />
          </Suspense>
        ),
      },
      {
        path: "agents",
        element: (
          <Suspense fallback={<LazyFallback />}>
            <ProtectedRoute requiredRole="admin">
              <AgentsPage />
            </ProtectedRoute>
          </Suspense>
        ),
      },
      {
        path: "threat-intel",
        element: (
          <Suspense fallback={<LazyFallback />}>
            <ThreatIntelPage />
          </Suspense>
        ),
      },
    ],
  },
  {
    path: "*",
    element: <Navigate to="/" replace />,
  },
])
