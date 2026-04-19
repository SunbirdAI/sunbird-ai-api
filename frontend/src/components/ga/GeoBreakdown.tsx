import type { GAGeoRow } from '../../hooks/useGoogleAnalytics';

interface Props {
  rows: GAGeoRow[];
}

export default function GeoBreakdown({ rows }: Props) {
  if (!rows.length) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">No geographic data.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 dark:border-white/10 text-left">
            <th className="py-2 px-3 font-medium text-gray-500 dark:text-gray-400">Country</th>
            <th className="py-2 px-3 font-medium text-gray-500 dark:text-gray-400">City</th>
            <th className="py-2 px-3 font-medium text-gray-500 dark:text-gray-400 text-right">Users</th>
            <th className="py-2 px-3 font-medium text-gray-500 dark:text-gray-400 text-right">Sessions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={`${r.country}-${r.city}`}
              className="border-b border-gray-100 dark:border-white/5 hover:bg-gray-50 dark:hover:bg-white/5"
            >
              <td className="py-2 px-3 text-gray-900 dark:text-white">{r.country || '—'}</td>
              <td className="py-2 px-3 text-gray-700 dark:text-gray-300">{r.city || '—'}</td>
              <td className="py-2 px-3 text-right text-gray-900 dark:text-white">
                {r.users.toLocaleString()}
              </td>
              <td className="py-2 px-3 text-right text-gray-700 dark:text-gray-300">
                {r.sessions.toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
