"use client";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { isWorkspace, routes, workspaceHref } from "../lib/workspace-routes";

export default function WorkspaceNav() {
  const pathname = usePathname();
  const params = useSearchParams();
  const ids = isWorkspace(pathname) ? params.getAll("paper") : [];
  return <>{[["Library",routes.library],["Search",routes.search],["Chat",routes.ask],["Compare",routes.compare]].map(
    ([label,path]) => <Link key={path} href={workspaceHref(path,ids)}>{label}</Link>
  )}</>;
}
