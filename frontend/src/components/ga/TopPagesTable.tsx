import type { GATopPage } from '../../hooks/useGoogleAnalytics';

interface Props {
  pages: GATopPage[];
}

export default function TopPagesTable({ pages }: Props) {
  if (!pages.length) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">No page views in this range.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 dark:border-white/10 text-left">
            <th className="py-2 px-3 font-medium text-gray-500 dark:text-gray-400">Page</th>
            <th className="py-2 px-3 font-medium text-gray-500 dark:text-gray-400 text-right">Views</th>
            <th className="py-2 px-3 font-medium text-gray-500 dark:text-gray-400 text-right">Users</th>
            <th className="py-2 px-3 font-medium text-gray-500 dark:text-gray-400 text-right">Avg duration</th>
          </tr>
        </thead>
        <tbody>
          {pages.map((p) => (
            <tr
              key={p.path}
              className="border-b border-gray-100 dark:border-white/5 hover:bg-gray-50 dark:hover:bg-white/5"
            >
              <td className="py-2 px-3">
                <div className="font-medium text-gray-900 dark:text-white">{p.title || p.path}</div>
                <div className="text-xs text-gray-500 dark:text-gray-400">{p.path}</div>
              </td>
              <td className="py-2 px-3 text-right text-gray-900 dark:text-white">
                {p.views.toLocaleString()}
              </td>
              <td className="py-2 px-3 text-right text-gray-900 dark:text-white">
                {p.users.toLocaleString()}
              </td>
              <td className="py-2 px-3 text-right text-gray-700 dark:text-gray-300">
                {p.avg_duration.toFixed(1)}s
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
