import { ReactNode } from 'react';
import { motion } from 'framer-motion';

interface ChartCardProps {
  title: string;
  description?: string;
  children: ReactNode;
  timeRange?: string;
  onTimeRangeChange?: (range: string) => void;
  showTimeSelector?: boolean;
  className?: string;
}

export default function ChartCard({
  title,
  description,
  children,
  timeRange = '7d',
  onTimeRangeChange,
  showTimeSelector = true,
  className = 'h-[300px]',
}: ChartCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-white dark:bg-secondary p-6 rounded-xl shadow-md dark:shadow-lg dark:shadow-black/10 border border-gray-200 dark:border-white/5"
    >
      <div className="flex items-start justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h2>
          {description && (
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{description}</p>
          )}
        </div>
        {showTimeSelector && onTimeRangeChange && (
          <select
            value={timeRange}
            onChange={(e) => onTimeRangeChange(e.target.value)}
            className="px-3 py-1.5 text-sm bg-white dark:bg-black/50 border border-gray-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 dark:text-white"
          >
            <option value="7d">Last 7 Days</option>
            <option value="30d">Last 30 Days</option>
            <option value="90d">Last 90 Days</option>
          </select>
        )}
      </div>
      <div className={`${className} flex flex-col`}>
        {children}
      </div>
    </motion.div>
  );
}
