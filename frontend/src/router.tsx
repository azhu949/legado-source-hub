/** 路由配置。 */

import { createBrowserRouter, type RouteObject } from "react-router-dom"
import { AdminLayout } from "@/components/layout/AdminLayout"
import LoginPage from "@/pages/LoginPage"
import DashboardPage from "@/pages/DashboardPage"
import AggregateSourcePage from "@/pages/AggregateSourcePage"
import SourceListPage from "@/pages/sources/SourceListPage"
import SourceEditPage from "@/pages/sources/SourceEditPage"
import SourceImportPage from "@/pages/sources/SourceImportPage"
import RuleTestPage from "@/pages/RuleTestPage"
import HealthPage from "@/pages/HealthPage"
import CachePage from "@/pages/CachePage"
import LogsPage from "@/pages/LogsPage"

export const router = createBrowserRouter([
  {
    path: "/admin/login",
    element: <LoginPage />,
  },
  {
    path: "/admin",
    element: <AdminLayout />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: "aggregate", element: <AggregateSourcePage /> },
      { path: "sources", element: <SourceListPage /> },
      { path: "sources/new", element: <SourceEditPage /> },
      { path: "sources/:id/edit", element: <SourceEditPage /> },
      { path: "sources/import", element: <SourceImportPage /> },
      { path: "rules/test", element: <RuleTestPage /> },
      { path: "health", element: <HealthPage /> },
      { path: "cache", element: <CachePage /> },
      { path: "logs", element: <LogsPage /> },
    ],
  },
  {
    path: "/",
    loader: () => {
      window.location.href = "/admin/login"
      return null
    },
  },
])
