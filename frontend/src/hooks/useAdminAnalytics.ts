import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';

export type ViewType = 'overview' | 'organization' | 'organization_type' | 'sector';

export interface FilterOptions {
  organizations: string[];
  organization_types: string[];
  sectors: string[];
}

export interface PerUserBreakdown {
  username: string;
  total_requests: number;
  endpoints: Record<string, number>;
}

export interface AdminAnalyticsData {
  usage: { endpoint: string; used: number }[];
  recent_activity: any[];
  chart_data: { labels: string[]; data: number[] };
  endpoint_chart_data: { labels: string[]; datasets: Record<string, number[]> };
  latency_chart: { labels: string[]; data: number[] };
  distribution_chart: { labels: string[]; data: number[] };
  latency_distribution: { labels: string[]; data: number[] };
  organization?: string;
  organization_type?: string;
  sector?: string;
  per_user_breakdown?: PerUserBreakdown[];
}

export function useAdminFilters() {
  const [filters, setFilters] = useState<FilterOptions | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchFilters = async () => {
      try {
        const response = await axios.get('/api/admin/analytics/filters');
        setFilters(response.data);
      } catch (err: any) {
        toast.error(err.response?.data?.detail?.message || 'Failed to fetch filter options');
      } finally {
        setLoading(false);
      }
    };
    fetchFilters();
  }, []);

  return { filters, loading };
}

export function useAdminAnalytics(
  view: ViewType,
  filterValue: string,
  timeRange: string = '7d'
) {
  const [data, setData] = useState<AdminAnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      let url = '/api/admin/analytics/';
      const params = new URLSearchParams({ time_range: timeRange });

      if (view === 'overview') {
        url += 'overview';
      } else if (view === 'organization') {
        url += 'by-organization';
        params.set('organization', filterValue);
      } else if (view === 'organization_type') {
        url += 'by-organization-type';
        params.set('organization_type', filterValue);
      } else if (view === 'sector') {
        url += 'by-sector';
        params.set('sector', filterValue);
      }

      const response = await axios.get(`${url}?${params.toString()}`);
      setData(response.data);
    } catch (err: any) {
      const msg = err.response?.data?.detail?.message || 'Failed to fetch analytics data';
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, [view, filterValue, timeRange]);

  useEffect(() => {
    // Only fetch if overview or filter value is provided
    if (view === 'overview' || filterValue) {
      fetchData();
    } else {
      setData(null);
      setLoading(false);
    }
  }, [view, filterValue, timeRange, fetchData]);

  return { data, loading, error };
}

export function useAdminExport() {
  const exportCSV = async (
    view: ViewType,
    timeRange: string,
    filterValue?: string
  ) => {
    try {
      const params = new URLSearchParams({ view, time_range: timeRange });
      if (view === 'organization' && filterValue) {
        params.set('organization', filterValue);
      } else if (view === 'organization_type' && filterValue) {
        params.set('organization_type', filterValue);
      } else if (view === 'sector' && filterValue) {
        params.set('sector', filterValue);
      }

      const response = await axios.get(
        `/api/admin/analytics/export?${params.toString()}`,
        { responseType: 'blob' }
      );

      const blob = new Blob([response.data], { type: 'text/csv' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `analytics_${view}_${timeRange}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);

      toast.success('CSV exported successfully');
    } catch (err: any) {
      toast.error('Failed to export CSV');
    }
  };

  return { exportCSV };
}
