import { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';

export interface UsageStat {
  endpoint: string;
  used: number;
  limit: number;
  reset: string;
}

export interface RecentActivity {
  id: number;
  username: string;
  endpoint: string;
  organization: string;
  time_taken: number;
  date: string;
}

export interface ChartData {
  labels: string[];
  data: number[];
}

export interface DashboardData {
  usage: UsageStat[];
  recent_activity: RecentActivity[];
  chart_data: ChartData;
  latency_chart: ChartData;
  distribution_chart: ChartData;
  account_type: string;
  organization: string;
}

export function useDashboardData() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await axios.get('/api/usage');
        setData(response.data);
        console.log(response.data);
      } catch (err: any) {
        const errorMessage = err.response?.data?.detail || 'Failed to fetch dashboard data';
        setError(errorMessage);
        toast.error(errorMessage);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  return { data, loading, error };
}
