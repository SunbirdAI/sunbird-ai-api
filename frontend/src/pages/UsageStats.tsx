import { ColumnDef } from '@tanstack/react-table';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
} from 'chart.js';
import { Bar, Line } from 'react-chartjs-2';
import DataTable from '../components/DataTable';
import { useDashboardData, UsageStat } from '../hooks/useDashboardData';

ChartJS.register(
  CategoryScale, 
  LinearScale, 
  BarElement,
  PointElement,
  LineElement,
  Title, 
  Tooltip, 
  Legend
);

export default function UsageStats() {
  const { data, loading } = useDashboardData();

  const chartData = {
    labels: data?.chart_data.labels || ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
    datasets: [
      {
        label: 'Total Requests',
        data: data?.chart_data.data || [0, 0, 0, 0, 0, 0, 0],
        backgroundColor: 'rgba(59, 130, 246, 0.5)',
        borderColor: 'rgb(59, 130, 246)',
        borderWidth: 1,
      },
    ],
  };

  const latencyData = {
    labels: data?.latency_chart.labels || [],
    datasets: [
      {
        label: 'Avg Latency (s)',
        data: data?.latency_chart.data || [],
        borderColor: 'rgb(249, 115, 22)',
        backgroundColor: 'rgba(249, 115, 22, 0.5)',
        tension: 0.4,
      },
    ],
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'top' as const,
        labels: {
          color: 'rgb(156, 163, 175)',
          font: {
            family: 'Google Sans, sans-serif',
          }
        }
      },
      title: {
        display: false,
      },
    },
    scales: {
      y: {
        grid: {
          color: 'rgba(156, 163, 175, 0.1)'
        },
        ticks: {
          color: 'rgb(156, 163, 175)',
          font: {
            family: 'Google Sans, sans-serif',
          }
        },
        beginAtZero: true,
      },
      x: {
        grid: {
          display: false
        },
        ticks: {
          color: 'rgb(156, 163, 175)',
          font: {
            family: 'Google Sans, sans-serif',
          }
        }
      }
    }
  };

  const usageColumns: ColumnDef<UsageStat>[] = [
    {
      accessorKey: 'endpoint',
      header: 'Endpoint',
    },
    {
      accessorKey: 'used',
      header: 'Used',
      cell: ({ row }) => row.original.used.toLocaleString()
    },
    {
      accessorKey: 'limit',
      header: 'Limit',
      cell: ({ row }) => row.original.limit.toLocaleString()
    },
    {
      accessorKey: 'reset',
      header: 'Reset Date',
    },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ row }) => (
        <div className="w-24 bg-gray-200 dark:bg-gray-700 rounded-full h-1.5">
          <div
            className="bg-primary-600 h-1.5 rounded-full"
            style={{ width: `${row.original.limit > 0 ? (row.original.used / row.original.limit) * 100 : 0}%` }}
          />
        </div>
      )
    },
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500 dark:text-gray-400">Loading usage stats...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Usage Statistics</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Detailed breakdown of your API usage.</p>
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white dark:bg-secondary rounded-xl p-6 shadow-md dark:shadow-lg dark:shadow-black/10 border border-gray-200 dark:border-white/5">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-6">Request Volume</h2>
          <div className="h-[300px]">
            <Bar options={chartOptions} data={chartData} />
          </div>
        </div>

        <div className="bg-white dark:bg-secondary rounded-xl p-6 shadow-md dark:shadow-lg dark:shadow-black/10 border border-gray-200 dark:border-white/5">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-6">Latency Trends</h2>
          <div className="h-[300px]">
            <Line options={chartOptions} data={latencyData} />
          </div>
        </div>
      </div>

      {/* Usage Breakdown Table */}
      <div className="bg-white dark:bg-secondary rounded-xl shadow-md dark:shadow-lg dark:shadow-black/10 border border-gray-200 dark:border-white/5 p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-6">Usage Breakdown</h2>
        <DataTable
          data={data?.usage || []}
          columns={usageColumns}
          itemsPerPage={10}
          searchable={true}
          emptyMessage="No usage data available"
        />
      </div>
    </div>
  );
}
