// The one piece of time handling the page does: showing an instant the API sent.
//
// Both formatters name their zone. Without `timeZone` the browser would use the
// visitor's own, and the page would say 02:00 to someone in Paris for the period
// that starts at 01:00 on a UK clock. The tests run with TZ=UTC (vite.config.ts) so
// that leaving it out is caught on any machine, including one set to UK time.

const OPTIONS: Intl.DateTimeFormatOptions = {
  hour: '2-digit',
  minute: '2-digit',
  timeZoneName: 'short',
}

const LOCAL = new Intl.DateTimeFormat('en-GB', { ...OPTIONS, timeZone: 'Europe/London' })
const UTC = new Intl.DateTimeFormat('en-GB', { ...OPTIONS, timeZone: 'UTC' })

/** "01:00 BST" or "01:00 GMT": the start on a UK clock. */
export function formatLocal(startUtc: string): string {
  return LOCAL.format(new Date(startUtc))
}

/** "01:00 UTC": the same instant, which is the period's identity. */
export function formatUtc(startUtc: string): string {
  return UTC.format(new Date(startUtc))
}
