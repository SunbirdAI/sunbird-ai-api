import { useState, useMemo, useEffect } from 'react';
import ChartCard from '../components/ChartCard';
import MetricCard from '../components/MetricCard';
import MultiSelect from '../components/MultiSelect';
import FilterBar from '../components/admin/FilterBar';
import {
  ViewType,
  useAdminAnalytics,
  useAdminFilters,
  useAdminExport,
} from '../hooks/useAdminAnalytics';
import { Activity, Clock, TrendingUp, Building2, Download } from 'lucide-react';
import { Skeleton } from '../components/ui/Skeleton';

import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import { Line } from 'react-chartjs-2';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

const COLOR_PALETTE = [
  '#E6194B', '#3CB44B', '#4363D8', '#F58231', '#911EB4',
  '#42D4F4', '#F032E6', '#469990', '#9A6324', '#800000',
  '#808000', '#000075', '#000000',
];

export default function AdminAnalytics() {
  const [timeRange, setTimeRange] = useState('7d');
  const [view, setView] = useState<ViewType>('overview');
  const [filterValue, setFilterValue] = useState('');

  const { filters, loading: filtersLoading } = useAdminFilters();
  const { data, loading } = useAdminAnalytics(view, filterValue, timeRange);
  const { exportCSV } = useAdminExport();

  // Endpoint colors
  const endpointColors = useMemo(() => {
    const colors: Record<string, string> = { 'Total': '#6B7280' };
    if (data?.endpoint_chart_data?.datasets) {
      const endpoints = Object.keys(data.endpoint_chart_data.datasets).sort();
      endpoints.forEach((endpoint, index) => {
        colors[endpoint] = COLOR_PALETTE[index % COLOR_PALETTE.length];
      });
    }
    return colors;
  }, [data]);

  // Visible endpoints state
  const [visibleEndpoints, setVisibleEndpoints] = useState<Record<string, boolean>>({
    'Total': true,
  });

  useEffect(() => {
    if (data?.endpoint_chart_data?.datasets) {
      setVisibleEndpoints((prev) => {
        const next = { ...prev };
        Object.keys(data.endpoint_chart_data.datasets).forEach((endpoint) => {
          if (next[endpoint] === undefined) {
            next[endpoint] = true;
          }
        });
        return next;
      });
    }
  }, [data]);

  const endpointOptions = useMemo(() => {
    const options = [
      { label: 'Total', value: 'Total', color: endpointColors['Total'] },
    ];
    if (data?.endpoint_chart_data?.datasets) {
      Object.keys(data.endpoint_chart_data.datasets)
        .sort()
        .forEach((endpoint) => {
          options.push({
            label: endpoint.replace('/v1/', ''),
            value: endpoint,
            color: endpointColors[endpoint],
          });
        });
    }
    return options;
  }, [data, endpointColors]);

  const selectedEndpoints = useMemo(
    () => Object.keys(visibleEndpoints).filter((ep) => visibleEndpoints[ep] !== false),
    [visibleEndpoints]
  );

  const handleSelectionChange = (selected: string[]) => {
    const newVisible: Record<string, boolean> = {};
    endpointOptions.forEach((opt) => {
      newVisible[opt.value] = selected.includes(opt.value);
    });
    setVisibleEndpoints(newVisible);
  };

  // Chart data
  const endpointDatasets = data?.endpoint_chart_data?.datasets || {};
  const volumeChartData = {
    labels: data?.endpoint_chart_data?.labels || data?.chart_data?.labels || [],
    datasets: [
      ...Object.entries(endpointDatasets).map(([endpoint, endpointData]) => ({
        label: endpoint,
        data: endpointData as number[],
        borderColor: endpointColors[endpoint] || '#6B7280',
        backgroundColor: 'transparent',
        tension: 0.4,
        borderWidth: 2,
        hidden: visibleEndpoints[endpoint] === false,
      })),
      {
        label: 'Total',
        data: data?.chart_data?.data || [],
        borderColor: '#6B7280',
        backgroundColor: 'transparent',
        borderWidth: 3,
        tension: 0.4,
        hidden: visibleEndpoints['Total'] === false,
      },
    ],
  };

  const latencyChartData = {
    labels: data?.latency_chart?.labels || [],
    datasets: [
      {
        label: 'Avg Latency (ms)',
        data: data?.latency_chart?.data?.map((val: number) => val * 1000) || [],
        fill: true,
        backgroundColor: (context: any) => {
          const ctx = context.chart.ctx;
          const gradient = ctx.createLinearGradient(0, 0, 0, 200);
          gradient.addColorStop(0, 'rgba(59, 130, 246, 0.2)');
          gradient.addColorStop(1, 'rgba(59, 130, 246, 0)');
          return gradient;
        },
        borderColor: '#3b82f6',
        tension: 0.4,
      },
    ],
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        mode: 'index' as const,
        intersect: false,
        backgroundColor: 'rgba(0, 0, 0, 0.8)',
        titleColor: '#fff',
        bodyColor: '#fff',
        borderColor: 'rgba(255, 255, 255, 0.1)',
        borderWidth: 1,
        padding: 10,
      },
    },
    scales: {
      x: {
        grid: { display: false },
        ticks: { color: 'rgba(156, 163, 175, 0.8)' },
      },
      y: {
        grid: { color: 'rgba(156, 163, 175, 0.1)' },
        ticks: { color: 'rgba(156, 163, 175, 0.8)' },
        beginAtZero: true,
      },
    },
    interaction: {
      mode: 'nearest' as const,
      axis: 'x' as const,
      intersect: false,
    },
  };

  // Metrics
  const totalRequests = data?.usage?.reduce((acc, curr) => acc + curr.used, 0) || 0;
  const avgLatency = data?.latency_chart?.data?.length
    ? (
        (data.latency_chart.data.reduce((a: number, b: number) => a + b, 0) /
          data.latency_chart.data.length) *
        1000
      ).toFixed(0)
    : '0';
  const mostUsedEndpoint = data?.usage?.reduce(
    (max: any, curr: any) => (curr.used > (max?.used || 0) ? curr : max),
    null
  );
  const uniqueOrgs = filters?.organizations?.length || 0;

  // Loading skeleton
  if (loading && !data) {
    return (
      <div className="space-y-6">
        <div className="flex flex-col gap-4">
          <Skeleton className="h-8 w-48 mb-2" />
          <Skeleton className="h-10 w-full max-w-xl" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="bg-white dark:bg-secondary p-6 rounded-xl border border-gray-200 dark:border-white/5 shadow-sm">
              <Skeleton className="h-8 w-8 rounded-lg mb-4" />
              <Skeleton className="h-8 w-32 mb-1" />
              <Skeleton className="h-3 w-16" />
            </div>
          ))}
        </div>
        <Skeleton className="h-[400px] w-full rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Admin Analytics</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Platform-wide API usage and performance analytics.
          </p>
        </div>
        <button
          onClick={() => exportCSV(view, timeRange, filterValue)}
          className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-sm font-medium"
        >
          <Download size={16} />
          Export CSV
        </button>
      </div>

      {/* Filter Bar */}
      <FilterBar
        view={view}
        onViewChange={setView}
        filterValue={filterValue}
        onFilterValueChange={setFilterValue}
        filters={filters}
        filtersLoading={filtersLoading}
      />

      {/* Prompt to select filter */}
      {view !== 'overview' && !filterValue && (
        <div className="text-center py-12 text-gray-500 dark:text-gray-400">
          <Building2 size={48} className="mx-auto mb-4 opacity-50" />
          <p className="text-lg font-medium">Select a filter value above to view analytics</p>
        </div>
      )}

      {/* Content (overview or filtered) */}
      {(view === 'overview' || filterValue) && data && (
        <>
          {/* Summary Metrics */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <MetricCard
              label="Total Requests"
              value={totalRequests.toLocaleString()}
              icon={Activity}
              color="bg-blue-500"
            />
            <MetricCard
              label="Avg Latency"
              value={`${avgLatency}ms`}
              icon={Clock}
              color="bg-orange-500"
            />
            <MetricCard
              label="Most Used"
              value={mostUsedEndpoint?.endpoint?.replace('/v1/', '') || 'N/A'}
              icon={TrendingUp}
              color="bg-purple-500"
            />
            <MetricCard
              label="Organizations"
              value={uniqueOrgs}
              icon={Building2}
              color="bg-green-500"
            />
          </div>

          {/* Charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Request Volume */}
            <div className="lg:col-span-2">
              <ChartCard
                title="Request Volume by Endpoint"
                description="Track usage trends across all users"
                showTimeSelector={true}
                timeRange={timeRange}
                onTimeRangeChange={setTimeRange}
                className="h-[400px]"
              >
                <div className="flex flex-wrap gap-3 mb-4 pb-4 border-b border-gray-200 dark:border-white/10">
                  <MultiSelect
                    label="Select Endpoints"
                    options={endpointOptions}
                    selected={selectedEndpoints}
                    onChange={handleSelectionChange}
                  />
                </div>
                <div className="flex-1 min-h-0">
                  <Line options={chartOptions} data={volumeChartData} />
                </div>
              </ChartCard>
            </div>

            {/* Latency Trends */}
            <ChartCard
              title="Latency Trends"
              description="Average response time over the selected period"
              showTimeSelector={true}
              timeRange={timeRange}
              onTimeRangeChange={setTimeRange}
            >
              <div className="flex-1 min-h-0">
                <Line options={chartOptions} data={latencyChartData} />
              </div>
            </ChartCard>

            {/* Endpoint Breakdown */}
            <div className="bg-white dark:bg-secondary rounded-xl shadow-md dark:shadow-lg dark:shadow-black/10 border border-gray-200 dark:border-white/5 p-6">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                Endpoint Breakdown
              </h3>
              <div className="space-y-3">
                {data?.usage
                  ?.filter((item) => item.endpoint !== 'unknown')
                  .sort((a, b) => b.used - a.used)
                  .map((item) => {
                    const percentage =
                      totalRequests > 0
                        ? ((item.used / totalRequests) * 100).toFixed(1)
                        : '0';
                    return (
                      <div key={item.endpoint} className="flex items-center justify-between">
                        <div className="flex items-center gap-3 flex-1">
                          <div
                            className="w-3 h-3 rounded-full flex-shrink-0"
                            style={{
                              backgroundColor: endpointColors[item.endpoint] || '#6B7280',
                            }}
                          />
                          <span className="text-sm text-gray-700 dark:text-gray-300">
                            {item.endpoint
                              .replace('/tasks/', '')
                              .replace('/tasks', 'tasks')}
                          </span>
                        </div>
                        <div className="flex items-center gap-4">
                          <span className="text-sm font-medium text-gray-900 dark:text-white">
                            {item.used.toLocaleString()}
                          </span>
                          <span className="text-sm text-gray-500 dark:text-gray-400 w-12 text-right">
                            {percentage}%
                          </span>
                        </div>
                      </div>
                    );
                  })}
              </div>
            </div>
          </div>

          {/* Per-user breakdown (organization view only) */}
          {data?.per_user_breakdown && data.per_user_breakdown.length > 0 && (
            <div className="bg-white dark:bg-secondary rounded-xl shadow-md dark:shadow-lg dark:shadow-black/10 border border-gray-200 dark:border-white/5 p-6">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                User Breakdown — {data.organization}
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 dark:border-white/10">
                      <th className="text-left py-3 px-4 font-medium text-gray-500 dark:text-gray-400">
                        Username
                      </th>
                      <th className="text-right py-3 px-4 font-medium text-gray-500 dark:text-gray-400">
                        Total Requests
                      </th>
                      <th className="text-left py-3 px-4 font-medium text-gray-500 dark:text-gray-400">
                        Top Endpoints
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.per_user_breakdown.map((user) => {
                      const topEndpoints = Object.entries(user.endpoints)
                        .sort(([, a], [, b]) => b - a)
                        .slice(0, 3);
                      return (
                        <tr
                          key={user.username}
                          className="border-b border-gray-100 dark:border-white/5 hover:bg-gray-50 dark:hover:bg-white/5"
                        >
                          <td className="py-3 px-4 text-gray-900 dark:text-white font-medium">
                            {user.username}
                          </td>
                          <td className="py-3 px-4 text-right text-gray-900 dark:text-white">
                            {user.total_requests.toLocaleString()}
                          </td>
                          <td className="py-3 px-4">
                            <div className="flex flex-wrap gap-1">
                              {topEndpoints.map(([ep, count]) => (
                                <span
                                  key={ep}
                                  className="inline-flex items-center px-2 py-0.5 rounded text-xs bg-gray-100 dark:bg-white/10 text-gray-700 dark:text-gray-300"
                                >
                                  {ep.replace('/tasks/', '')}: {count}
                                </span>
                              ))}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
