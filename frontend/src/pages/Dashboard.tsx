import { useState, useEffect, useMemo } from 'react';
import ChartCard from '../components/ChartCard';
import MetricCard from '../components/MetricCard';
import MultiSelect from '../components/MultiSelect';
import { useDashboardData } from '../hooks/useDashboardData';
import { Activity, Clock, TrendingUp } from 'lucide-react';
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

const ENDPOINT_COLORS = {
  'Total': '#6B7280', // Gray
};



const COLOR_PALETTE = [
  '#E6194B', // Red
  '#3CB44B', // Green
  '#4363D8', // Blue
  '#F58231', // Orange
  '#911EB4', // Purple
  '#42D4F4', // Cyan
  '#F032E6', // Magenta
  '#469990', // Teal
  '#9A6324', // Brown
  '#800000', // Maroon
  '#808000', // Olive
  '#000075', // Navy
  '#000000', // Black
];

export default function Dashboard() {
  const { data, loading } = useDashboardData('7d');
  
  // Generate consistent colors for endpoints based on the current data
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

  // State for toggling endpoint visibility
  const [visibleEndpoints, setVisibleEndpoints] = useState<Record<string, boolean>>({
    'Total': true,
  });

  // Initialize visible endpoints when data loads
  useEffect(() => {
    if (data?.endpoint_chart_data?.datasets) {
      setVisibleEndpoints(prev => {
        const next = { ...prev };
        Object.keys(data.endpoint_chart_data.datasets).forEach(endpoint => {
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
      { label: 'Total', value: 'Total', color: endpointColors['Total'] }
    ];
    
    if (data?.endpoint_chart_data?.datasets) {
      const endpoints = Object.keys(data.endpoint_chart_data.datasets).sort();
      endpoints.forEach(endpoint => {
        options.push({
          label: endpoint.replace('/v1/', ''),
          value: endpoint,
          color: endpointColors[endpoint]
        });
      });
    }
    return options;
  }, [data, endpointColors]);

  const selectedEndpoints = useMemo(() => {
    return Object.keys(visibleEndpoints).filter(ep => visibleEndpoints[ep] !== false);
  }, [visibleEndpoints]);

  const handleSelectionChange = (selected: string[]) => {
    const newVisible: Record<string, boolean> = {};
    endpointOptions.forEach(opt => {
      newVisible[opt.value] = selected.includes(opt.value);
    });
    setVisibleEndpoints(newVisible);
  };

  // Multi-line Request Volume Chart Data
  const endpointDatasets = data?.endpoint_chart_data?.datasets || {};
  const volumeChartData = {
    labels: data?.endpoint_chart_data?.labels || data?.chart_data?.labels || [],
    datasets: [
      // Individual endpoint datasets
      ...Object.entries(endpointDatasets).map(([endpoint, endpointData]) => ({
        label: endpoint,
        data: endpointData as number[],
        borderColor: endpointColors[endpoint] || '#6B7280',
        backgroundColor: 'transparent',
        tension: 0.4,
        borderWidth: 2,
        hidden: visibleEndpoints[endpoint] === false,
      })),
      // Total dataset
      {
        label: 'Total',
        data: data?.chart_data?.data || [],
        borderColor: ENDPOINT_COLORS['Total'],
        backgroundColor: 'transparent',
        borderWidth: 3,
        tension: 0.4,
        hidden: visibleEndpoints['Total'] === false,
      },
    ],
  };

  // Latency Chart Data
  const latencyChartData = {
    labels: data?.latency_chart.labels || [],
    datasets: [
      {
        label: 'Avg Latency (ms)',
        data: data?.latency_chart.data.map((val: number) => val * 1000) || [],
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
      legend: {
        display: false,
      },
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
        grid: {
          display: false,
        },
        ticks: {
          color: 'rgba(156, 163, 175, 0.8)',
        },
      },
      y: {
        grid: {
          color: 'rgba(156, 163, 175, 0.1)',
        },
        ticks: {
          color: 'rgba(156, 163, 175, 0.8)',
        },
        beginAtZero: true,
      },
    },
    interaction: {
      mode: 'nearest' as const,
      axis: 'x' as const,
      intersect: false,
    },
  };

  if (loading) {
    return (
      <div className="space-y-6 ">
        {/* Header Skeleton */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <Skeleton className="h-8 w-48 mb-2" />
            <Skeleton className="h-4 w-64" />
          </div>
          {/* <div className="flex items-center gap-3">
            <Skeleton className="h-10 w-32" />
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-gray-200 dark:border-white/5 shadow-sm bg-white dark:bg-secondary">
               <Loader2 className="w-4 h-4 animate-spin text-primary-500" />
               <span className="text-sm text-gray-500 dark:text-gray-400">Loading...</span>
            </div>
          </div> */}
        </div>

        {/* Metrics Skeleton */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-white dark:bg-secondary p-6 rounded-xl border border-gray-200 dark:border-white/5 shadow-sm">
              <div className="flex items-center justify-between mb-4">
                {/* <Skeleton className="h-4 w-24" /> */}
                <Skeleton className="h-8 w-8 rounded-lg" />
              </div>
              <Skeleton className="h-8 w-32 mb-1" />
              <Skeleton className="h-3 w-16" />
            </div>
          ))}
        </div>

        {/* Charts Skeleton */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="lg:col-span-2 bg-white dark:bg-secondary p-6 rounded-xl border border-gray-200 dark:border-white/5 shadow-sm h-[400px] flex flex-col">
             <div className="flex justify-between mb-6">
               <div>
                 <Skeleton className="h-6 w-48 mb-2" />
                 <Skeleton className="h-4 w-64" />
               </div>
             </div>
             <Skeleton className="h-10 w-48 mb-4" />
             <Skeleton className="w-full flex-1 rounded-lg" />
          </div>

          <div className="bg-white dark:bg-secondary p-6 rounded-xl border border-gray-200 dark:border-white/5 shadow-sm h-[300px] flex flex-col">
             <Skeleton className="h-6 w-32 mb-2" />
             <Skeleton className="h-4 w-48 mb-6" />
             <Skeleton className="w-full flex-1 rounded-lg" />
          </div>

          <div className="bg-white dark:bg-secondary p-6 rounded-xl border border-gray-200 dark:border-white/5 shadow-sm h-[300px]">
             <Skeleton className="h-6 w-48 mb-4" />
             <div className="space-y-4">
               {[1, 2, 3, 4].map(i => (
                 <div key={i} className="flex justify-between items-center">
                   <div className="flex items-center gap-3">
                     <Skeleton className="h-3 w-3 rounded-full" />
                     <Skeleton className="h-4 w-20" />
                   </div>
                   <Skeleton className="h-4 w-16" />
                 </div>
               ))}
             </div>
          </div>
        </div>
      </div>
    );
  }

  // Calculate metrics
  const totalRequests = data?.usage.reduce((acc: number, curr: any) => acc + curr.used, 0) || 0;
  const avgLatency = data?.latency_chart.data.length 
    ? (data.latency_chart.data.reduce((a: number, b: number) => a + b, 0) / data.latency_chart.data.length * 1000).toFixed(0)
    : '0';
  
  // Find most used endpoint
  const mostUsedEndpoint = data?.usage.reduce((max: any, curr: any) => 
    curr.used > (max?.used || 0) ? curr : max, null);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Dashboard</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Overview of your API usage and performance.</p>
        </div>
        {/* <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400 bg-white dark:bg-secondary px-3 py-1.5 rounded-lg border border-gray-200 dark:border-white/5 shadow-sm">
            <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            System Operational
          </div>
        </div> */}
      </div>

      {/* Summary Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
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
          value={mostUsedEndpoint?.endpoint.replace('/v1/', '') || 'N/A'}
          icon={TrendingUp}
          color="bg-purple-500"
        />
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Multi-line Request Volume Chart */}
        <div className="lg:col-span-2">
          <ChartCard
            title="Request Volume by Endpoint"
            description="Track usage trends for each API endpoint"
            showTimeSelector={false}
            className="h-[400px]"
          >
            {/* Legend/Toggle Controls */}
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

        {/* Latency Trends Chart */}
        <ChartCard
          title="Latency Trends"
          description="Average response time over the selected period"
          showTimeSelector={false}
        >
          <div className="flex-1 min-h-0">
            <Line options={chartOptions} data={latencyChartData} />
          </div>
        </ChartCard>

        {/* Endpoint Usage Table */}
        <div className="bg-white dark:bg-secondary rounded-xl shadow-md dark:shadow-lg dark:shadow-black/10 border border-gray-200 dark:border-white/5 p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Endpoint Breakdown</h3>
          <div className="space-y-3">
            {data?.usage.map((item: any) => {
              const percentage = totalRequests > 0 ? ((item.used / totalRequests) * 100).toFixed(1) : '0';
              return (
                <div key={item.endpoint} className="flex items-center justify-between">
                  <div className="flex items-center gap-3 flex-1">
                    <div
                      className="w-3 h-3 rounded-full flex-shrink-0"
                      style={{ backgroundColor: endpointColors[item.endpoint] || '#6B7280' }}
                    />
                    <span className="text-sm text-gray-700 dark:text-gray-300">
                      {item.endpoint}
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
    </div>
  );
}
