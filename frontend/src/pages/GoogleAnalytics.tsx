import { useEffect, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Activity, Clock, TrendingUp, Users as UsersIcon, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
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
import { Skeleton } from '../components/ui/Skeleton';
import ChartCard from '../components/ChartCard';
import MetricCard from '../components/MetricCard';
import { useGAOverview, useGAProperties } from '../hooks/useGoogleAnalytics';
import TrafficChart from '../components/ga/TrafficChart';
import TopPagesTable from '../components/ga/TopPagesTable';
import PlatformBreakdown from '../components/ga/PlatformBreakdown';
import GeoBreakdown from '../components/ga/GeoBreakdown';
import EventsTable from '../components/ga/EventsTable';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
);

const TIME_RANGES = [
  { label: 'Last 24h', value: '24h' },
  { label: 'Last 7 days', value: '7d' },
  { label: 'Last 30 days', value: '30d' },
  { label: 'Last 60 days', value: '60d' },
  { label: 'Last 90 days', value: '90d' },
];

export default function GoogleAnalytics() {
  const { properties, loading: propsLoading, notConfigured } = useGAProperties();
  const [searchParams, setSearchParams] = useSearchParams();

  const propertyId = searchParams.get('property') || '';
  const timeRange = searchParams.get('range') || '7d';

  useEffect(() => {
    if (!propertyId && properties.length > 0) {
      setSearchParams(
        { property: properties[0].id, range: timeRange },
        { replace: true },
      );
    }
  }, [properties, propertyId, timeRange, setSearchParams]);

  const { data, loading, error, refresh } = useGAOverview(propertyId, timeRange);

  const totals = useMemo(() => {
    if (!data) return null;
    const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);
    const avg = (xs: number[]) => (xs.length ? sum(xs) / xs.length : 0);
    return {
      users: sum(data.traffic.active_users),
      sessions: sum(data.traffic.sessions),
      engagementRate: avg(data.traffic.engagement_rate),
      avgSessionSec: avg(data.traffic.avg_session_duration),
    };
  }, [data]);

  if (notConfigured) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-500 dark:text-gray-400">
          Google Analytics is not configured. See <code>docs/google-analytics.md</code>.
        </p>
      </div>
    );
  }

  if (propsLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-10 w-full max-w-xl" />
        <Skeleton className="h-[400px] w-full rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Google Analytics</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Site & app analytics for Sunbird properties.
          </p>
        </div>
        <button
          onClick={() => {
            refresh();
            toast.info('Refreshing from Google Analytics…');
          }}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors text-sm font-medium"
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      <div className="flex flex-wrap gap-3 items-center">
        <select
          value={propertyId}
          onChange={(e) =>
            setSearchParams({ property: e.target.value, range: timeRange })
          }
          className="px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-secondary text-sm"
        >
          {properties.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>

        <select
          value={timeRange}
          onChange={(e) =>
            setSearchParams({ property: propertyId, range: e.target.value })
          }
          className="px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-secondary text-sm"
        >
          {TIME_RANGES.map((r) => (
            <option key={r.value} value={r.value}>{r.label}</option>
          ))}
        </select>

        {data && (
          <span className="text-xs text-gray-500 dark:text-gray-400 ml-auto">
            Cached until {new Date(data.cached_until).toLocaleTimeString()}
          </span>
        )}
      </div>

      {loading && !data && (
        <Skeleton className="h-[400px] w-full rounded-xl" />
      )}

      {error && !data && (
        <div className="p-4 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 text-sm">
          {error}
        </div>
      )}

      {data && totals && (
        <>
          {data.partial && (
            <div className="p-3 rounded-lg bg-amber-50 dark:bg-amber-900/20 text-amber-800 dark:text-amber-200 text-sm">
              Some reports failed to load: {data.failed_reports.join(', ')}.
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <MetricCard label="Users" value={totals.users.toLocaleString()} icon={UsersIcon} color="bg-blue-500" />
            <MetricCard label="Sessions" value={totals.sessions.toLocaleString()} icon={Activity} color="bg-orange-500" />
            <MetricCard label="Engagement" value={`${(totals.engagementRate * 100).toFixed(1)}%`} icon={TrendingUp} color="bg-purple-500" />
            <MetricCard label="Avg session" value={`${totals.avgSessionSec.toFixed(0)}s`} icon={Clock} color="bg-green-500" />
          </div>

          <ChartCard
            title="Traffic over time"
            description={`Active users, new users, sessions for ${data.property_name}`}
            className="h-[400px]"
          >
            <TrafficChart series={data.traffic} />
          </ChartCard>

          <div className="bg-white dark:bg-secondary rounded-xl shadow-md border border-gray-200 dark:border-white/5 p-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Top pages</h3>
            <TopPagesTable pages={data.top_pages} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-white dark:bg-secondary rounded-xl shadow-md border border-gray-200 dark:border-white/5 p-6">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Platforms</h3>
              <PlatformBreakdown platforms={data.platforms} />
            </div>

            <div className="bg-white dark:bg-secondary rounded-xl shadow-md border border-gray-200 dark:border-white/5 p-6">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Geography</h3>
              <GeoBreakdown rows={data.geography} />
            </div>
          </div>

          <div className="bg-white dark:bg-secondary rounded-xl shadow-md border border-gray-200 dark:border-white/5 p-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Top events</h3>
            <EventsTable events={data.events} />
          </div>
        </>
      )}
    </div>
  );
}
