export function bypassesClerk(pathname: string): boolean {
  return pathname === "/api/cron/retention";
}
