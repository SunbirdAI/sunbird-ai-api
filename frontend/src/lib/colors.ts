// Endpoint color palette with good contrast and accessibility
export const ENDPOINT_COLORS = [
  '#DC7828', // Primary orange
  '#3b82f6', // Blue
  '#10b981', // Green  
  '#8b5cf6', // Purple
  '#f59e0b', // Amber
  '#ec4899', // Pink
  '#14b8a6', // Teal
  '#f97316', // Orange variant
  '#6366f1', // Indigo
  '#84cc16', // Lime
];

// Get color for endpoint by index
export function getEndpointColor(index: number): string {
  return ENDPOINT_COLORS[index % ENDPOINT_COLORS.length];
}

// Status code color mapping
export const STATUS_COLORS = {
  '2xx': {
    bg: 'bg-green-100 dark:bg-green-900/30',
    text: 'text-green-800 dark:text-green-400',
    chart: '#10b981', // Green
  },
  '3xx': {
    bg: 'bg-blue-100 dark:bg-blue-900/30',
    text: 'text-blue-800 dark:text-blue-400',
    chart: '#3b82f6', // Blue
  },
  '4xx': {
    bg: 'bg-orange-100 dark:bg-orange-900/30',
    text: 'text-orange-800 dark:text-orange-400',
    chart: '#f59e0b', // Orange
  },
  '5xx': {
    bg: 'bg-red-100 dark:bg-red-900/30',
    text: 'text-red-800 dark:text-red-400',
    chart: '#ef4444', // Red
  },
};

// Get status category (2xx, 3xx, 4xx, 5xx)
export function getStatusCategory(statusCode: number): '2xx' | '3xx' | '4xx' | '5xx' {
  if (statusCode >= 200 && statusCode < 300) return '2xx';
  if (statusCode >= 300 && statusCode < 400) return '3xx';
  if (statusCode >= 400 && statusCode < 500) return '4xx';
  return '5xx';
}
