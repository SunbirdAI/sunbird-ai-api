import { Line } from 'react-chartjs-2';
import type { GATrafficSeries } from '../../hooks/useGoogleAnalytics';

interface Props {
  series: GATrafficSeries;
}

export default function TrafficChart({ series }: Props) {
  const data = {
    labels: series.labels,
    datasets: [
      {
        label: 'Active users',
        data: series.active_users,
        borderColor: '#3b82f6',
        backgroundColor: 'rgba(59,130,246,0.15)',
        tension: 0.4,
      },
      {
        label: 'New users',
        data: series.new_users,
        borderColor: '#10b981',
        backgroundColor: 'rgba(16,185,129,0.1)',
        tension: 0.4,
      },
      {
        label: 'Sessions',
        data: series.sessions,
        borderColor: '#f59e0b',
        backgroundColor: 'rgba(245,158,11,0.1)',
        tension: 0.4,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { position: 'top' as const } },
    interaction: { mode: 'index' as const, intersect: false },
    scales: {
      y: { beginAtZero: true, grid: { color: 'rgba(156,163,175,0.1)' } },
      x: { grid: { display: false } },
    },
  };

  return (
    <div className="h-[300px]">
      <Line data={data} options={options} />
    </div>
  );
}
