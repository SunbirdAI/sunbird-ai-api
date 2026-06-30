import { useState } from 'react';
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement,
  ArcElement, Title, Tooltip, Legend, Filler,
} from 'chart.js';
import { Line, Pie } from 'react-chartjs-2';
import { DollarSign, Clock, HardDrive, Server, Download, Info } from 'lucide-react';
import MetricCard from '../components/MetricCard';
import ChartCard from '../components/ChartCard';
import { Skeleton } from '../components/ui/Skeleton';
import {
  BillingFilters,
  useBillingSummary,
  useBillingTimeseries,
  useBillingProviders,
  useBillingTable,
  useBillingExport,
} from '../hooks/useBillingAnalytics';

ChartJS.register(
  CategoryScale, LinearScale, PointElement, LineElement, ArcElement,
  Title, Tooltip, Legend, Filler
);

const RANGES = [
  ['today', 'Today'], ['yesterday', 'Yesterday'], ['last_7_days', 'Last 7 Days'],
  ['last_30_days', 'Last 30 Days'], ['last_90_days', 'Last 90 Days'],
  ['this_month', 'This Month'], ['last_month', 'Last Month'],
] as const;

const PROVIDER_COLORS: Record<string, string> = { runpod: '#4363D8', modal: '#F58231' };

type SortCol = 'timestamp' | 'cost';

export default function AdminBilling() {
  const [filters, setFilters] = useState<BillingFilters>({
    provider: 'all', range: 'last_30_days', resolution: 'day',
  });
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState<SortCol>('cost');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  const { data: summary, loading: summaryLoading } = useBillingSummary(filters);
  const { data: timeseries } = useBillingTimeseries(filters);
  const { data: providers } = useBillingProviders(filters);
  const { data: table } = useBillingTable(filters, page, sort, sortDir);
  const { exportCSV } = useBillingExport();

  const set = (patch: Partial<BillingFilters>) => {
    setFilters((f) => ({ ...f, ...patch }));
    setPage(1);
  };

  const toggleSort = (col: SortCol) => {
    if (sort === col) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSort(col);
      setSortDir('desc');
    }
    setPage(1);
  };

  const sortArrow = (col: SortCol) =>
    sort === col ? (sortDir === 'asc' ? ' ▲' : ' ▼') : '';

  // One line per platform (from cost_by_group) plus a dashed Total line.
  const costByGroup = timeseries?.cost_by_group || {};
  const costLine = {
    labels: timeseries?.labels || [],
    datasets: [
      ...Object.entries(costByGroup).map(([prov, data]) => ({
        label: prov,
        data: data as number[],
        borderColor: PROVIDER_COLORS[prov] || '#6B7280',
        backgroundColor: 'transparent',
        borderWidth: 2,
        tension: 0.4,
      })),
      {
        label: 'Total',
        data: timeseries?.cost || [],
        borderColor: '#6B7280',
        backgroundColor: 'transparent',
        borderWidth: 3,
        borderDash: [5, 5],
        tension: 0.4,
      },
    ],
  };

  const platformPie = {
    labels: providers?.labels || [],
    datasets: [{
      data: providers?.cost || [],
      backgroundColor: (providers?.labels || []).map((l) => PROVIDER_COLORS[l] || '#6B7280'),
    }],
  };

  const chartOptions = {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { display: true, labels: { color: 'rgba(156,163,175,0.9)' } } },
    scales: {
      x: { grid: { display: false }, ticks: { color: 'rgba(156,163,175,0.8)' } },
      y: { grid: { color: 'rgba(156,163,175,0.1)' }, beginAtZero: true,
           ticks: { color: 'rgba(156,163,175,0.8)' } },
    },
  };

  if (summaryLoading && !summary) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-28 rounded-xl" />)}
        </div>
        <Skeleton className="h-[400px] w-full rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Infrastructure Billing
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Runpod & Modal spend, runtime, and storage analytics.
          </p>
        </div>
        <button
          onClick={() => exportCSV(filters)}
          className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 text-sm font-medium"
        >
          <Download size={16} /> Export CSV
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <select
          value={filters.provider}
          onChange={(e) => set({ provider: e.target.value as BillingFilters['provider'] })}
          className="px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-secondary text-sm"
        >
          <option value="all">All Platforms</option>
          <option value="runpod">Runpod</option>
          <option value="modal">Modal</option>
        </select>
        <select
          value={filters.range}
          onChange={(e) => set({ range: e.target.value })}
          className="px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-secondary text-sm"
        >
          {RANGES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
        </select>
        <select
          value={filters.resolution}
          onChange={(e) => set({ resolution: e.target.value as BillingFilters['resolution'] })}
          className="px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-secondary text-sm"
        >
          {['hour', 'day', 'week', 'month', 'year'].map((r) =>
            <option key={r} value={r}>{r[0].toUpperCase() + r.slice(1)}</option>)}
        </select>
      </div>

      {summary?.warnings?.map((w) => (
        <div key={w} className="text-sm text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 px-4 py-2 rounded-lg">
          {w}
        </div>
      ))}

      {/* Summary cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <MetricCard label="Total Spend" value={`$${(summary?.total_spend || 0).toFixed(2)}`} icon={DollarSign} color="bg-blue-500" />
        <MetricCard label="Avg Daily Spend" value={`$${(summary?.avg_daily_spend || 0).toFixed(2)}`} icon={DollarSign} color="bg-green-500" />
        <MetricCard label="Compute Time" value={`${((summary?.total_runtime_ms || 0) / 3_600_000).toFixed(1)}h`} icon={Clock} color="bg-orange-500" />
        <MetricCard label="Avg Storage" value={`${(summary?.avg_storage_gb || 0).toFixed(0)} GB`} icon={HardDrive} color="bg-purple-500" />
      </div>

      {/* What these numbers mean */}
      <details className="bg-white dark:bg-secondary rounded-xl border border-gray-200 dark:border-white/5 p-4 text-sm text-gray-600 dark:text-gray-300">
        <summary className="flex items-center gap-2 cursor-pointer font-medium text-gray-900 dark:text-white">
          <Info size={16} /> What these numbers mean &amp; how they're computed
        </summary>
        <div className="mt-3 space-y-2 leading-relaxed">
          <p><b>Total / Avg Daily Spend</b> — USD billed by the provider for the selected
            range and platform(s), summed across all records. Modal amounts are pre-credit
            (before any credits or reservations), so your invoice may be lower.</p>
          <p><b>Compute Time</b> — total billed run time, from Runpod's <code>timeBilledMs</code>
            (worker-time across the period). Modal bills per-app cost and does not report a
            runtime, so this reflects Runpod only.</p>
          <p><b>Avg Storage (GB)</b> — providers bill storage as <b>GB-hours</b> (capacity ×
            hours billed), so a steady 350&nbsp;GB volume reports 350&nbsp;×&nbsp;24&nbsp;=&nbsp;8,400 per
            day. We show the time-weighted average — total GB-hours ÷ hours in the range — as
            actual provisioned GB. The records table and CSV show the raw per-bucket GB-hours.</p>
          <p><b>Active Endpoints / Modal Apps</b> — distinct Runpod endpoints and Modal apps
            with billing in the range. <b>Network Volumes</b> are account-level storage, not an
            endpoint, so they're excluded from this count (but included in spend/storage).</p>
          <p><b>Network Volumes</b> — Runpod persistent network storage cost
            (<code>/billing/networkvolumes</code>), shown as its own row and folded into totals.</p>
          <p><b>Cost Over Time</b> — per-bucket spend with a line per platform plus a dashed
            Total. Buckets roll up to the selected resolution (hour → year).</p>
          <p className="text-gray-500 dark:text-gray-400">Scope &amp; freshness: Runpod is scoped
            to the configured endpoints; Modal covers the whole workspace. Figures are cached
            briefly for consistency, so very recent usage settles within the cache window.</p>
        </div>
      </details>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="lg:col-span-2">
          <ChartCard title="Cost Over Time" description="Spend per bucket across selected platforms" className="h-[400px]">
            <div className="flex-1 min-h-0"><Line options={chartOptions} data={costLine} /></div>
          </ChartCard>
        </div>
        <ChartCard title="Spend by Platform" description="Runpod vs Modal">
          <div className="flex-1 min-h-0 flex items-center justify-center">
            <Pie data={platformPie} options={{ responsive: true, maintainAspectRatio: false }} />
          </div>
        </ChartCard>
        <div className="bg-white dark:bg-secondary rounded-xl border border-gray-200 dark:border-white/5 p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">Highlights</h3>
          <ul className="text-sm text-gray-700 dark:text-gray-300 space-y-2">
            <li>Active endpoints: <b>{summary?.active_endpoints ?? 0}</b></li>
            <li>Active Modal apps: <b>{summary?.active_modal_apps ?? 0}</b></li>
            <li>Top endpoint: <b>{summary?.highest_cost_endpoint?.name ?? 'N/A'}</b> (${(summary?.highest_cost_endpoint?.cost ?? 0).toFixed(2)})</li>
            <li>Top platform: <b>{summary?.highest_cost_platform?.name ?? 'N/A'}</b> (${(summary?.highest_cost_platform?.cost ?? 0).toFixed(2)})</li>
          </ul>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white dark:bg-secondary rounded-xl border border-gray-200 dark:border-white/5 p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <Server size={18} /> Billing Records
          </h3>
          <input
            type="text" placeholder="Search object / GPU / env..."
            onChange={(e) => set({ search: e.target.value || undefined })}
            className="px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-secondary text-sm"
          />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 dark:border-white/10 text-left text-gray-500 dark:text-gray-400">
                <th className="py-2 px-3">Provider</th><th className="py-2 px-3">Object</th>
                <th
                  className="py-2 px-3 cursor-pointer select-none hover:text-gray-700 dark:hover:text-gray-200"
                  onClick={() => toggleSort('timestamp')}
                >
                  Date{sortArrow('timestamp')}
                </th>
                <th
                  className="py-2 px-3 text-right cursor-pointer select-none hover:text-gray-700 dark:hover:text-gray-200"
                  onClick={() => toggleSort('cost')}
                >
                  Cost{sortArrow('cost')}
                </th>
                <th className="py-2 px-3">GPU</th><th className="py-2 px-3">Env</th>
              </tr>
            </thead>
            <tbody>
              {(table?.rows || []).map((r, i) => (
                <tr
                  key={`${r.provider}-${r.object_name}-${r.timestamp}-${i}`}
                  className="border-b border-gray-100 dark:border-white/5"
                >
                  <td className="py-2 px-3">{r.provider}</td>
                  <td className="py-2 px-3">{r.object_name}</td>
                  <td className="py-2 px-3">{r.timestamp.slice(0, 10)}</td>
                  <td className="py-2 px-3 text-right">${r.cost.toFixed(4)}</td>
                  <td className="py-2 px-3">{r.gpu || '-'}</td>
                  <td className="py-2 px-3">{r.environment || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex items-center justify-between mt-4 text-sm text-gray-500 dark:text-gray-400">
          <span>{table?.total ?? 0} records</span>
          <div className="flex gap-2">
            <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}
              className="px-3 py-1 rounded border border-gray-200 dark:border-white/10 disabled:opacity-40">Prev</button>
            <button disabled={!table || page * table.page_size >= table.total}
              onClick={() => setPage((p) => p + 1)}
              className="px-3 py-1 rounded border border-gray-200 dark:border-white/10 disabled:opacity-40">Next</button>
          </div>
        </div>
      </div>
    </div>
  );
}
