import { ViewType, FilterOptions } from '../../hooks/useAdminAnalytics';

interface FilterBarProps {
  view: ViewType;
  onViewChange: (view: ViewType) => void;
  filterValue: string;
  onFilterValueChange: (value: string) => void;
  filters: FilterOptions | null;
  filtersLoading: boolean;
}

const VIEW_OPTIONS: { label: string; value: ViewType }[] = [
  { label: 'Overview', value: 'overview' },
  { label: 'By Organization', value: 'organization' },
  { label: 'By Org Type', value: 'organization_type' },
  { label: 'By Sector', value: 'sector' },
];

export default function FilterBar({
  view,
  onViewChange,
  filterValue,
  onFilterValueChange,
  filters,
  filtersLoading,
}: FilterBarProps) {
  const getFilterOptions = (): string[] => {
    if (!filters) return [];
    if (view === 'organization') return filters.organizations;
    if (view === 'organization_type') return filters.organization_types;
    if (view === 'sector') return filters.sectors;
    return [];
  };

  const filterOptions = getFilterOptions();
  const showFilterDropdown = view !== 'overview';

  const getFilterLabel = (): string => {
    if (view === 'organization') return 'Organization';
    if (view === 'organization_type') return 'Organization Type';
    if (view === 'sector') return 'Sector';
    return '';
  };

  return (
    <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
      {/* View selector */}
      <div className="flex items-center gap-1 bg-white dark:bg-secondary rounded-lg border border-gray-200 dark:border-white/10 p-1">
        {VIEW_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => {
              onViewChange(opt.value);
              onFilterValueChange('');
            }}
            className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
              view === opt.value
                ? 'bg-primary-600 text-white'
                : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/5'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* Filter value dropdown */}
      {showFilterDropdown && (
        <select
          value={filterValue}
          onChange={(e) => onFilterValueChange(e.target.value)}
          disabled={filtersLoading || filterOptions.length === 0}
          className="px-3 py-2 text-sm bg-white dark:bg-secondary border border-gray-200 dark:border-white/10 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 dark:text-white min-w-[200px]"
        >
          <option value="">Select {getFilterLabel()}...</option>
          {filterOptions.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}
