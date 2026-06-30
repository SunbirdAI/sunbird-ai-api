import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';

const BASE = '/api/admin/analytics/billing';

export interface BillingFilters {
  provider: 'all' | 'runpod' | 'modal';
  range: string;
  resolution: 'hour' | 'day' | 'week' | 'month' | 'year';
  groupBy?: string;
  search?: string;
}

export interface SummaryData {
  total_spend: number;
  avg_daily_spend: number;
  total_runtime_ms: number;
  avg_daily_runtime_ms: number;
  total_storage_gb: number;
  avg_storage_gb: number;
  active_endpoints: number;
  active_modal_apps: number;
  highest_cost_endpoint?: { name: string; cost: number } | null;
  highest_cost_platform?: { name: string; cost: number } | null;
  num_days: number;
  warnings: string[];
}

export interface TimeseriesData {
  labels: string[];
  cost: number[];
  runtime_ms: number[];
  storage_gb: number[];
  cost_by_group: Record<string, number[]>;
  warnings: string[];
}

export interface ProvidersData {
  labels: string[];
  cost: number[];
  runtime_ms: number[];
  storage_gb: number[];
  warnings: string[];
}

export interface BillingRow {
  provider: string;
  object_name: string;
  timestamp: string;
  cost: number;
  runtime_ms: number | null;
  storage_gb: number | null;
  gpu: string | null;
  environment: string | null;
  tags: Record<string, string>;
}

export interface TableData {
  rows: BillingRow[];
  total: number;
  page: number;
  page_size: number;
  warnings: string[];
}

function params(f: BillingFilters, extra: Record<string, string> = {}) {
  const p = new URLSearchParams({
    provider: f.provider,
    range: f.range,
    resolution: f.resolution,
    ...extra,
  });
  return p;
}

function useEndpoint<T>(path: string, f: BillingFilters, extra: Record<string, string> = {}) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const extraKey = JSON.stringify(extra);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const p = params(f, JSON.parse(extraKey));
      const resp = await axios.get(`${BASE}${path}?${p.toString()}`);
      setData(resp.data);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { message?: string } } };
      toast.error(axiosErr.response?.data?.message || `Failed to load ${path}`);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, f.provider, f.range, f.resolution, extraKey]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, loading };
}

export const useBillingSummary = (f: BillingFilters) =>
  useEndpoint<SummaryData>('/summary', f);

export const useBillingTimeseries = (f: BillingFilters) =>
  // Group by provider so the chart can draw a line per platform (cost_by_group).
  useEndpoint<TimeseriesData>('/timeseries', f, { group_by: f.groupBy || 'provider' });

export const useBillingProviders = (f: BillingFilters) =>
  useEndpoint<ProvidersData>('/providers', f);

export const useBillingTable = (
  f: BillingFilters,
  page: number,
  sort: string,
  sortDir: 'asc' | 'desc'
) =>
  useEndpoint<TableData>('/table', f, {
    page: String(page),
    page_size: '50',
    sort,
    sort_dir: sortDir,
    ...(f.search ? { search: f.search } : {}),
  });

export function useBillingExport() {
  const exportCSV = async (f: BillingFilters) => {
    try {
      const p = params(f);
      const resp = await axios.get(`${BASE}/export?${p.toString()}`, {
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([resp.data], { type: 'text/csv' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = `billing_${f.provider}_${f.resolution}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
      toast.success('CSV exported');
    } catch {
      toast.error('Failed to export CSV');
    }
  };
  return { exportCSV };
}
