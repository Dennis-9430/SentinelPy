import { Link, Outlet, useLocation } from "react-router-dom"
import { useAuth } from "../hooks/useAuth"
import { cn } from "../lib/utils"

const navItems = [
  { to: "/", label: "Dashboard", icon: "📊" },
  { to: "/events", label: "Events", icon: "📋" },
  { to: "/alerts", label: "Alerts", icon: "🔔" },
  { to: "/rules", label: "Rules", icon: "⚙️" },
  { to: "/users", label: "Users", icon: "👥" },
]

export function Layout() {
  const { pathname } = useLocation()
  const { user, logout } = useAuth()

  return (
    <div className="flex h-screen">
      {/* Sidebar */}
      <aside className="flex w-64 flex-col border-r bg-card">
        <div className="flex h-14 items-center gap-2 border-b px-4 font-bold">
          <span className="text-lg">SentinelPy</span>
        </div>
        <nav className="flex-1 space-y-1 p-2">
          {navItems.map((item) => {
            const isActive =
              item.to === "/" ? pathname === "/" : pathname.startsWith(item.to)
            return (
              <Link
                key={item.to}
                to={item.to}
                className={cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-accent text-accent-foreground font-medium"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                )}
              >
                <span>{item.icon}</span>
                <span>{item.label}</span>
              </Link>
            )
          })}
        </nav>
      </aside>

      {/* Main area */}
      <div className="flex flex-1 flex-col">
        {/* Topbar */}
        <header className="flex h-14 items-center justify-end gap-4 border-b px-6">
          <span className="text-sm text-muted-foreground">
            {user?.username}
          </span>
          <span className="inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium">
            {user?.role}
          </span>
          <button
            onClick={logout}
            className="text-sm text-muted-foreground underline-offset-2 hover:underline"
          >
            Logout
          </button>
        </header>

        {/* Content */}
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
