import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';

export interface GAProperty {
  id: string;
  name: string;
}

export interface GATrafficSeries {
  labels: string[];
  active_users: number[];
  new_users: number[];
  sessions: number[];
  engaged_sessions: number[];
  engagement_rate: number[];
  avg_session_duration: number[];
  bounce_rate: number[];
}

export interface GATopPage {
  path: string;
  title: string;
  views: number;
  users: number;
  avg_duration: number;
}

export interface GAPlatformRow {
  label: string;
  users: number;
  sessions: number;
}

export interface GAPlatforms {
  device: GAPlatformRow[];
  os: GAPlatformRow[];
  browser: GAPlatformRow[];
}

export interface GAGeoRow {
  country: string;
  city: string;
  users: number;
  sessions: number;
}

export interface GAEventRow {
  name: string;
  count: number;
  users: number;
}

export interface GAOverview {
  property_id: string;
  property_name: string;
  time_range: string;
  cached_until: string;
  traffic: GATrafficSeries;
  top_pages: GATopPage[];
  platforms: GAPlatforms;
  geography: GAGeoRow[];
  events: GAEventRow[];
  partial: boolean;
  failed_reports: string[];
}

const BASE = '/api/admin/google-analytics';

export function useGAProperties() {
  const [properties, setProperties] = useState<GAProperty[]>([]);
  const [loading, setLoading] = useState(true);
  const [notConfigured, setNotConfigured] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await axios.get(`${BASE}/properties`);
        if (!cancelled) setProperties(data.properties);
      } catch (err: any) {
        if (err?.response?.status === 503) {
          if (!cancelled) setNotConfigured(true);
        } else {
          toast.error('Failed to load GA properties');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return { properties, loading, notConfigured };
}

export function useGAOverview(propertyId: string, timeRange: string) {
  const [data, setData] = useState<GAOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchOverview = useCallback(
    async (force = false) => {
      if (!propertyId) return;
      setLoading(true);
      setError(null);
      try {
        const url = force ? `${BASE}/refresh` : `${BASE}/overview`;
        const { data: payload } = await axios({
          method: force ? 'post' : 'get',
          url,
          params: { property_id: propertyId, time_range: timeRange },
        });
        setData(payload);
      } catch (err: any) {
        const msg = err?.response?.data?.detail || 'Failed to load analytics';
        setError(typeof msg === 'string' ? msg : 'Failed to load analytics');
        toast.error(typeof msg === 'string' ? msg : 'Failed to load analytics');
      } finally {
        setLoading(false);
      }
    },
    [propertyId, timeRange],
  );

  useEffect(() => {
    fetchOverview(false);
  }, [fetchOverview]);

  return {
    data,
    loading,
    error,
    refresh: () => fetchOverview(true),
  };
}
