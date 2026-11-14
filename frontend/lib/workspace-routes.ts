export const routes = {library:"/library", search:"/search", ask:"/chat", compare:"/compare"} as const;
export type View = keyof typeof routes;

export function isWorkspace(path: string) {
  return Object.values(routes).some(route => route === path);
}

export function workspaceHref(path: string, ids: string[]) {
  if (!ids.length || !isWorkspace(path)) return path;
  const params = new URLSearchParams();
  ids.forEach(id => params.append("paper", id));
  return path + "?" + params.toString();
}
