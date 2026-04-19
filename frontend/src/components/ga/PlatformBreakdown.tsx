import type { GAPlatforms, GAPlatformRow } from '../../hooks/useGoogleAnalytics';

interface Props {
  platforms: GAPlatforms;
}

function PlatformList({ title, rows }: { title: string; rows: GAPlatformRow[] }) {
  const total = rows.reduce((acc, r) => acc + r.users, 0);
  return (
    <div>
      <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-200 mb-2">{title}</h4>
      {rows.length === 0 ? (
        <p className="text-xs text-gray-500">No data.</p>
      ) : (
        <ul className="space-y-1">
          {rows.map((r) => {
            const pct = total ? ((r.users / total) * 100).toFixed(1) : '0';
            return (
              <li key={r.label} className="flex items-center justify-between text-sm">
                <span className="text-gray-700 dark:text-gray-300">{r.label}</span>
                <span className="text-gray-900 dark:text-white font-medium">
                  {r.users.toLocaleString()}{' '}
                  <span className="text-xs text-gray-500">({pct}%)</span>
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export default function PlatformBreakdown({ platforms }: Props) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      <PlatformList title="Device" rows={platforms.device} />
      <PlatformList title="Operating system" rows={platforms.os} />
      <PlatformList title="Browser" rows={platforms.browser} />
    </div>
  );
}
