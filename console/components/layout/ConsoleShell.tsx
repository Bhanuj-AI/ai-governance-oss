"use client";

import Image from "next/image";
import Link from "next/link";
import {
  Activity,
  Boxes,
  Cpu,
  BookOpen,
  BriefcaseBusiness,
  FlaskConical,
  RotateCcw,
  FileSearch,
  Home,
  Network,
  ListRestart,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  Building2,
  ExternalLink,
  SlidersHorizontal,
  UserRound,
  LogOut,
  Moon,
  Sun,
  Route,
} from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listOrganizations, listProjects } from "@/lib/api/tenancy";
import { useTenantContext } from "@/components/tenancy/TenantContextProvider";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils/cn";
import { useAuth } from "@/auth/auth-provider";
import { STUDIO_NAVIGATION_CONTRIBUTIONS } from "@/extensions/navigation";

const OSS_NAV_ITEMS = [
  {
    href: "/",
    icon: <Home className="h-4 w-4" />,
    label: "Home",
    enabled: true,
  },
  {
    href: "/organization",
    icon: <Building2 className="h-4 w-4" />,
    label: "Organization",
    enabled: true,
  },
  {
    href: "/assets",
    icon: <Boxes className="h-4 w-4" />,
    label: "Assets",
    enabled: true,
  },
  {
    href: "/agents-runtime",
    icon: <Cpu className="h-4 w-4" />,
    label: "Agents Runtime",
    enabled: true,
  },
  {
    href: "/graph",
    icon: <Network className="h-4 w-4" />,
    label: "Ontology",
    enabled: true,
  },
  {
    href: "/policies",
    icon: <SlidersHorizontal className="h-4 w-4" />,
    label: "Policies Engine",
    enabled: true,
  },
  {
    href: "/experiments",
    icon: <FlaskConical className="h-4 w-4" />,
    label: "Experiments",
    enabled: true,
  },
  {
    href: "/replays",
    icon: <RotateCcw className="h-4 w-4" />,
    label: "Replay",
    enabled: true,
  },
  {
    href: "/decisions",
    icon: <FileSearch className="h-4 w-4" />,
    label: "Decisions",
    enabled: true,
  },
  {
    href: "/graph/synchronization",
    icon: <ListRestart className="h-4 w-4" />,
    label: "Sync Events",
    enabled: true,
  },
  {
    href: "/jobs",
    icon: <BriefcaseBusiness className="h-4 w-4" />,
    label: "Jobs",
    enabled: true,
  },
  {
    href: "/audit",
    icon: <Activity className="h-4 w-4" />,
    label: "MCP Audit Ledger",
    enabled: true,
  },
  {
    href: "/settings",
    icon: <Settings className="h-4 w-4" />,
    label: "Settings",
    enabled: true,
  },
];

const NAV_ITEMS = [...OSS_NAV_ITEMS, ...STUDIO_NAVIGATION_CONTRIBUTIONS];

const NAVIGATION_COLLAPSED_KEY = "ai_governance.navigation.collapsed";
const THEME_KEY = "ai_governance.theme";

export function StudioShell({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(() =>
    typeof window !== "undefined" &&
    window.localStorage.getItem(NAVIGATION_COLLAPSED_KEY) === "true",
  );
  const [profileOpen, setProfileOpen] = useState(false);
  const [darkMode, setDarkMode] = useState(() =>
    typeof window !== "undefined" && window.localStorage.getItem(THEME_KEY) === "dark",
  );
  const profileRef = useRef<HTMLDivElement>(null);
  const tenant = useTenantContext();
  const auth = useAuth();
  const organizations = useQuery({ queryKey: ["organizations"], queryFn: listOrganizations });
  const projects = useQuery({ queryKey: ["projects", tenant.organizationId],
    queryFn: () => listProjects(tenant.organizationId), enabled: Boolean(tenant.organizationId) });

  // Every route renders the shell independently, so keep this preference in
  // local storage instead of allowing navigation to reset it.
  useEffect(() => {
    window.localStorage.setItem(NAVIGATION_COLLAPSED_KEY, String(collapsed));
  }, [collapsed]);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", darkMode);
    window.localStorage.setItem(THEME_KEY, darkMode ? "dark" : "light");
  }, [darkMode]);

  useEffect(() => {
    if (!profileOpen) return;

    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!profileRef.current?.contains(event.target as Node)) {
        setProfileOpen(false);
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setProfileOpen(false);
    };

    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [profileOpen]);

  return (
    <div className="min-h-screen bg-background">
      <header className="flex min-h-16 flex-wrap items-center justify-between gap-3 border-b bg-card px-5 py-3">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <span className="flex h-11 w-11 items-center justify-center overflow-hidden rounded-md p-1">
            <Image
              src="/ai-governance-logo.png"
              alt="AI Governance Control Plane logo"
              width={64}
              height={64}
              className="h-full w-full object-contain"
              priority
            />
          </span>
          AI Governance Control Plane Studio
        </Link>
        <div className="flex flex-1 flex-wrap items-center justify-end gap-3">
          <ContextSelector label="Organization" value={tenant.organizationId}
            options={(organizations.data || []).map(item => ({ id: item.organization_id, label: item.name }))}
            onChange={tenant.selectOrganization} />
          <ContextSelector label="Project" value={tenant.projectId}
            options={(projects.data || []).filter(item => item.status === "ACTIVE").map(item => ({ id: item.project_id, label: item.name }))}
            onChange={tenant.selectProject} />
          <button
            type="button"
            className="flex h-9 w-9 items-center justify-center rounded-full border bg-background text-foreground shadow-sm hover:bg-accent"
            aria-label={darkMode ? "Use light theme" : "Use dark theme"}
            title={darkMode ? "Use light theme" : "Use dark theme"}
            onClick={() => setDarkMode((value) => !value)}
          >
            {darkMode ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
          <div ref={profileRef} className="relative">
            <button
              type="button"
              className="flex h-9 w-9 items-center justify-center rounded-full border bg-background text-foreground shadow-sm"
              aria-label="Open account menu"
              aria-expanded={profileOpen}
              title="Account menu"
              onClick={() => setProfileOpen((value) => !value)}
            >
              <UserRound className="h-4 w-4" />
            </button>
            {profileOpen ? (
              <div className="absolute right-0 top-11 z-50 w-60 rounded-md border bg-card p-2 shadow-lg">
                <div className="border-b px-3 pb-2">
                  <div className="text-xs text-muted-foreground">Signed in as</div>
                  <div className="mt-1 truncate text-sm font-medium">{auth.username ?? "Authenticated user"}</div>
                </div>
                <Link
                  href="/journey"
                  onClick={() => setProfileOpen(false)}
                  className="mt-2 flex items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-accent"
                >
                  <Route className="h-4 w-4" />
                  Guided journeys
                </Link>
                <button
                  type="button"
                  className="mt-2 flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-destructive hover:bg-accent"
                  onClick={() => void auth.logout()}
                >
                  <LogOut className="h-4 w-4" />
                  Sign out
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </header>
      <div
        className={cn(
          "grid min-h-[calc(100vh-4rem)] grid-cols-1 transition-[grid-template-columns] duration-200 lg:grid-cols-[220px_1fr]",
          collapsed && "lg:grid-cols-[64px_1fr]",
        )}
      >
        <aside
          className={cn(
            "border-b bg-card px-3 py-3 transition-[padding] duration-200 lg:border-b-0 lg:border-r lg:py-4",
            collapsed ? "lg:px-2" : "lg:px-3",
          )}
        >
          {!collapsed ? (
            <div className="mb-3 px-3 lg:mb-4">
              <div className="text-xs font-semibold uppercase tracking-normal text-muted-foreground">
                Navigation
              </div>
            </div>
          ) : null}
          <div
            className={cn(
              "mb-3 hidden lg:flex",
              collapsed ? "justify-center" : "justify-end",
            )}
          >
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
              title={collapsed ? "Expand navigation" : "Collapse navigation"}
              onClick={() => setCollapsed((value) => !value)}
            >
              {collapsed ? (
                <PanelLeftOpen className="h-4 w-4" />
              ) : (
                <PanelLeftClose className="h-4 w-4" />
              )}
            </Button>
          </div>
          <nav className="flex gap-1 overflow-x-auto lg:flex-col lg:overflow-visible">
            {NAV_ITEMS.map((item) => (
              <NavLink key={item.href} {...item} collapsed={collapsed} />
            ))}
          </nav>
          {!collapsed ? (
            <div className="hidden lg:block">
              <Separator className="my-4" />
              <Link
                href="/journey"
                className="flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
              >
                <Route className="h-4 w-4" />
                Guided journeys
              </Link>
              <a
                href="https://governance.bhanuj.ai/docs"
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
              >
                <BookOpen className="h-4 w-4" />
                Documentation
                <ExternalLink className="ml-auto h-3.5 w-3.5 text-muted-foreground" />
              </a>
              <div className="px-3 text-xs leading-5 text-muted-foreground">
                Governance operations for the selected organization and
                project.
              </div>
            </div>
          ) : (
            <div className="mt-4 hidden justify-center lg:flex">
              <div
                className="h-1.5 w-1.5 rounded-full bg-primary/65"
                title="Navigation collapsed"
              />
            </div>
          )}
        </aside>
        <main className="min-w-0">{children}</main>
      </div>
    </div>
  );
}

export function ConsoleShell({ children }: { children: React.ReactNode }) {
  return <StudioShell>{children}</StudioShell>;
}

function ContextSelector({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { id: string; label: string }[];
  onChange: (id: string) => void;
}) {
  return (
    <label
      className="flex h-9 max-w-full items-center gap-2 rounded-md border bg-background px-3 text-left text-sm shadow-sm hover:bg-accent"
      title={`${label}: ${value}`}
    >
      <span className="hidden text-muted-foreground sm:inline">{label}:</span>
      <select aria-label={label} value={value} onChange={event => onChange(event.target.value)}
        className="max-w-[190px] bg-transparent font-medium outline-none">
        {!value ? <option value="">Select {label.toLowerCase()}</option> : null}
        {options.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}
      </select>
    </label>
  );
}

function NavLink({
  href,
  icon,
  label,
  enabled,
  collapsed,
}: {
  href: string;
  icon: React.ReactNode;
  label: string;
  enabled?: boolean;
  collapsed: boolean;
}) {
  const pathname = usePathname();
  const active = href === "/"
    ? pathname === "/"
    : href === "/graph"
      ? pathname === "/graph"
      : pathname.startsWith(href);

  if (!enabled) {
    return (
      <button
        type="button"
        disabled
        aria-label={collapsed ? label : undefined}
        title={collapsed ? label : `${label} will be available later`}
        className={cn(
          "flex h-9 shrink-0 items-center rounded-md text-sm font-medium text-muted-foreground opacity-65",
          collapsed ? "gap-2 px-3 lg:justify-center lg:px-0" : "gap-2 px-3",
        )}
      >
        {icon}
        <span className={collapsed ? "lg:hidden" : undefined}>{label}</span>
      </button>
    );
  }

  return (
    <Link
      href={href}
      aria-label={collapsed ? label : undefined}
      title={collapsed ? label : undefined}
      className={cn(
        "flex h-9 shrink-0 items-center rounded-md text-sm font-medium text-foreground hover:bg-accent hover:text-accent-foreground",
        collapsed ? "gap-2 px-3 lg:justify-center lg:px-0" : "gap-2 px-3",
        active && "bg-accent text-accent-foreground",
      )}
    >
      {icon}
      <span className={collapsed ? "lg:hidden" : undefined}>{label}</span>
    </Link>
  );
}
