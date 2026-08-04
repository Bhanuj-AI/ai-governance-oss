import Link from "next/link";
export function OrganizationNav() {
  return <nav className="flex gap-2 border-b pb-3 text-sm">
    <Link className="rounded-md px-3 py-2 hover:bg-accent" href="/organization">Overview</Link>
    <Link className="rounded-md px-3 py-2 hover:bg-accent" href="/organization/projects">Projects</Link>
    <Link className="rounded-md px-3 py-2 hover:bg-accent" href="/organization/members">Members</Link>
    <Link className="rounded-md px-3 py-2 hover:bg-accent" href="/organization/access">Access</Link>
  </nav>;
}
