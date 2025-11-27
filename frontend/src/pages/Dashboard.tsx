import { ColumnDef } from '@tanstack/react-table';
import { motion } from 'framer-motion';
import { Activity, ChevronRight } from 'lucide-react';
import DataTable from '../components/DataTable';
import { Link } from 'react-router-dom';
import { useDashboardData } from '../hooks/useDashboardData';
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
  ArcElement,
} from 'chart.js';
import { Line, Doughnut } from 'react-chartjs-2';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
  ArcElement
);

interface RecentCall {
  id: string;
  endpoint: string;
  status: number;
  latency: string;
  time: string;
}

export default function Dashboard() {
  const { data, loading } = useDashboardData();
  
  const recentCalls: RecentCall[] = data?.recent_activity.map(log => ({
    id: log.id.toString(),
    endpoint: log.endpoint,
    status: 200, // TODO: Add status code to logs
    latency: `${(log.time_taken * 1000).toFixed(0)}ms`,
    time: new Date(log.date).toLocaleString()
  })) || [];

  const chartData = {
    labels: data?.chart_data.labels || ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
    datasets: [
      {
        label: 'Total Requests',
        data: data?.chart_data.data || [0, 0, 0, 0, 0, 0, 0],
        fill: true,
        backgroundColor: (context: any) => {
          const ctx = context.chart.ctx;
          const gradient = ctx.createLinearGradient(0, 0, 0, 200);
          gradient.addColorStop(0, 'rgba(220, 120, 40, 0.2)');
          gradient.addColorStop(1, 'rgba(220, 120, 40, 0)');
          return gradient;
        },
        borderColor: '#DC7828',
        tension: 0.4,
      },
    ],
  };

  const distributionData = {
    labels: data?.distribution_chart.labels || [],
    datasets: [
      {
        data: data?.distribution_chart.data || [],
        backgroundColor: [
          'rgba(220, 120, 40, 0.8)',
          'rgba(59, 130, 246, 0.8)',
          'rgba(16, 185, 129, 0.8)',
          'rgba(139, 92, 246, 0.8)',
        ],
        borderColor: [
          'rgba(220, 120, 40, 1)',
          'rgba(59, 130, 246, 1)',
          'rgba(16, 185, 129, 1)',
          'rgba(139, 92, 246, 1)',
        ],
        borderWidth: 1,
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
        displayColors: false,
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
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500 dark:text-gray-400">Loading dashboard...</div>
      </div>
    );
  }

  // Calculate total requests
  const totalRequests = data?.usage.reduce((acc, curr) => acc + curr.used, 0) || 0;

  const stats = [
    {
      label: 'Total Requests',
      value: totalRequests.toLocaleString(),
      icon: Activity,
      color: 'bg-blue-500',
      change: '+12%'
    },
    {
      label: 'Success Rate',
      value: '99.9%',
      icon: Activity,
      color: 'bg-green-500',
      change: '+0.2%'
    },
    {
      label: 'Active Keys',
      value: '1',
      icon: Activity,
      color: 'bg-purple-500',
      change: null
    },
    {
      label: 'Avg Latency',
      value: '245ms',
      icon: Activity,
      color: 'bg-orange-500',
      change: '-5%'
    }
  ];

  const recentActivityColumns: ColumnDef<RecentCall>[] = [
    {
      accessorKey: 'endpoint',
      header: 'Endpoint',
    },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ row }) => (
        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
          row.original.status === 200 
            ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400' 
            : 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400'
        }`}>
          {row.original.status}
        </span>
      )
    },
    {
      accessorKey: 'latency',
      header: 'Latency',
    },
    {
      accessorKey: 'time',
      header: 'Time',
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Dashboard</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Overview of your API usage and performance.</p>
        </div>
        <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400 bg-white dark:bg-secondary px-3 py-1.5 rounded-lg border border-gray-200 dark:border-white/5 shadow-sm">
          <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
          System Operational
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat, index) => (
          <motion.div
            key={stat.label}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.1 }}
            className="bg-white dark:bg-secondary p-6 rounded-xl shadow-sm border border-gray-100 dark:border-white/5 hover:border-primary-500/20 transition-colors group"
          >
            <div className="flex items-center justify-between mb-4">
              <div className={`p-2 rounded-lg ${stat.color} bg-opacity-10 dark:bg-opacity-20 group-hover:scale-110 transition-transform`}>
                <stat.icon className={`w-5 h-5 ${stat.color.replace('bg-', 'text-')}`} />
              </div>
              {stat.change && (
                <span className="text-xs font-medium text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900/20 px-2 py-1 rounded-full">
                  {stat.change}
                </span>
              )}
            </div>
            <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">{stat.label}</h3>
            <p className="text-2xl font-bold text-gray-900 dark:text-white mt-1">{stat.value}</p>
          </motion.div>
        ))}
      </div>

      {/* Charts Section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="bg-white dark:bg-secondary p-6 rounded-xl shadow-sm border border-gray-100 dark:border-white/5"
        >
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-6">Request Volume</h2>
          <div className="h-[300px] flex items-center justify-center">
             <Line options={chartOptions} data={chartData} />
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="bg-white dark:bg-secondary p-6 rounded-xl shadow-sm border border-gray-100 dark:border-white/5"
        >
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-6">Endpoint Distribution</h2>
          <div className="h-[300px] flex items-center justify-center">
             <Doughnut data={distributionData} options={{ maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } } }} />
          </div>
        </motion.div>
      </div>

      {/* Recent Activity */}
      <div className="bg-white dark:bg-secondary rounded-xl shadow-md dark:shadow-lg dark:shadow-black/10 border border-gray-200 dark:border-white/5 p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <Activity className="w-5 h-5 text-gray-500 dark:text-gray-400" />
            Recent Activity
          </h2>
          <Link 
            to="/usage"
            className="text-sm text-primary-600 dark:text-primary-400 hover:underline flex items-center gap-1"
          >
            View All <ChevronRight className="w-3 h-3" />
          </Link>
        </div>
        <DataTable
          data={recentCalls}
          columns={recentActivityColumns}
          itemsPerPage={5}
          searchable={true}
          emptyMessage="No recent activity. Start making API calls to see them here."
        />
      </div>
    </div>
  );
}
