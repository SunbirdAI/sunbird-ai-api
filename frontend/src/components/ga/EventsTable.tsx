import type { GAEventRow } from '../../hooks/useGoogleAnalytics';

interface Props {
  events: GAEventRow[];
}

export default function EventsTable({ events }: Props) {
  if (!events.length) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">No events in this range.</p>;
  }

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-gray-200 dark:border-white/10 text-left">
          <th className="py-2 px-3 font-medium text-gray-500 dark:text-gray-400">Event</th>
          <th className="py-2 px-3 font-medium text-gray-500 dark:text-gray-400 text-right">Count</th>
          <th className="py-2 px-3 font-medium text-gray-500 dark:text-gray-400 text-right">Users</th>
        </tr>
      </thead>
      <tbody>
        {events.map((e) => (
          <tr
            key={e.name}
            className="border-b border-gray-100 dark:border-white/5 hover:bg-gray-50 dark:hover:bg-white/5"
          >
            <td className="py-2 px-3 text-gray-900 dark:text-white font-mono text-xs">
              {e.name}
            </td>
            <td className="py-2 px-3 text-right text-gray-900 dark:text-white">
              {e.count.toLocaleString()}
            </td>
            <td className="py-2 px-3 text-right text-gray-700 dark:text-gray-300">
              {e.users.toLocaleString()}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
