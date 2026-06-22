import { motion } from 'framer-motion';
import {
  ExternalLink,
  Info,
  Flame,
  PlayCircle,
  Filter,
  MessageSquare,
  ThumbsUp,
  LineChart as LineChartIcon,
  UserCog,
  Users,
  Zap,
  Mail,
  Lock,
} from 'lucide-react';

const HOTJAR_URL = 'https://insights.hotjar.com';

const SIGN_IN_EMAILS = ['info@sunbird.ai', 'analytics@sunbird.ai'];

type Feature = {
  name: string;
  icon: typeof Flame;
  color: string;
  description: string;
  useFor: string;
};

const FEATURES: Feature[] = [
  {
    name: 'Heatmaps',
    icon: Flame,
    color: 'bg-orange-500',
    description:
      'Aggregate click, move, scroll, and rage-click maps overlaid on each page. Shows where visitors focus attention and where they drop off.',
    useFor:
      'Spot unclicked CTAs, dead zones, and content that never gets scrolled into view.',
  },
  {
    name: 'Session Recordings',
    icon: PlayCircle,
    color: 'bg-red-500',
    description:
      'Replay real user sessions with cursor movement, clicks, taps, scrolls, and form interactions. Filter by country, device, page, rage click, or u-turn.',
    useFor:
      'Debug confusing UX, watch how real users navigate sign-up, and confirm a bug is reproducible in the wild.',
  },
  {
    name: 'Funnels',
    icon: Filter,
    color: 'bg-purple-500',
    description:
      'Multi-step conversion funnels defined by URL patterns or events. Drop-off rate is shown per step with linked recordings for each stage.',
    useFor:
      'Measure landing-page → register → first API call conversion, and watch recordings of users who dropped off.',
  },
  {
    name: 'Surveys',
    icon: MessageSquare,
    color: 'bg-blue-500',
    description:
      'On-site and link surveys (NPS, CSAT, CES, exit-intent, custom). Trigger on URL, time on page, scroll depth, or exit intent.',
    useFor:
      'Ask "What were you hoping to find?" on pages with high bounce, or NPS on the dashboard.',
  },
  {
    name: 'Feedback Widget',
    icon: ThumbsUp,
    color: 'bg-green-500',
    description:
      'Inline rating widget (0–5 stars / emoji) pinned to any page. Visitors pick a rating, leave a comment, and optionally highlight the exact element they are commenting on.',
    useFor:
      'Passive, continuous sentiment signal per page. Great for the pricing and docs pages.',
  },
  {
    name: 'Trends & Dashboards',
    icon: LineChartIcon,
    color: 'bg-indigo-500',
    description:
      'Aggregate trends over time: page-level NPS, CSAT, feedback score, rage clicks, u-turns, conversion rate. Composable dashboards.',
    useFor:
      'Track whether the last release moved the needle on rage-clicks or feedback scores.',
  },
  {
    name: 'User Attributes',
    icon: UserCog,
    color: 'bg-teal-500',
    description:
      'Custom identifiers (user_id, plan, organization, role) sent via the Hotjar JS SDK and used to filter and segment every other tool.',
    useFor:
      'Filter recordings to "admin users on the Speech product who hit an error" without leaking PII.',
  },
  {
    name: 'Engage (Interviews)',
    icon: Users,
    color: 'bg-pink-500',
    description:
      'Schedule moderated user interviews with calendar integration and automatic incentive delivery. Recruit from the existing visitor pool.',
    useFor:
      'Book a live session with a real user who just rage-clicked the upload flow.',
  },
  {
    name: 'Integrations',
    icon: Zap,
    color: 'bg-amber-500',
    description:
      'Native integrations with Slack, Jira, Linear, Microsoft Teams, Google Analytics, Segment, HubSpot, Zapier, and more.',
    useFor:
      'Pipe new survey responses into the #product Slack channel, or link a recording to a Jira ticket.',
  },
];

export default function EngagementInsights() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Website &amp; Engagement Funnel
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Qualitative website insights for all Sunbird products, powered by Hotjar.
          </p>
        </div>
        <a
          href={HOTJAR_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-sm font-medium shadow-sm"
        >
          Open Hotjar Insights
          <ExternalLink size={16} />
        </a>
      </div>

      {/* Why external */}
      <div className="flex items-start gap-3 p-4 rounded-xl bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800/40 text-amber-900 dark:text-amber-100 text-sm">
        <Info size={18} className="flex-shrink-0 mt-0.5" />
        <div>
          <p className="font-medium">Why open Hotjar instead of viewing the data here?</p>
          <p className="mt-1 text-amber-800 dark:text-amber-200/90">
            Hotjar&apos;s public API only exposes a limited subset of administrative data
            (users, sites, survey metadata). Heatmaps, recordings, funnel drop-offs, and
            survey responses are only viewable inside the Hotjar dashboard. We therefore
            link out rather than maintain a partial mirror that would miss the
            highest-value insights.
          </p>
        </div>
      </div>

      {/* Sign-in instructions */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-white dark:bg-secondary rounded-xl shadow-sm border border-gray-100 dark:border-white/5 p-6"
      >
        <div className="flex items-start gap-3">
          <div className="p-2 rounded-lg bg-primary-500 bg-opacity-10 dark:bg-opacity-20">
            <Lock className="w-5 h-5 text-primary-600 dark:text-primary-400" />
          </div>
          <div className="flex-1">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              How to sign in
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              Hotjar access is tied to two shared Sunbird Google accounts. Use
              <span className="font-medium"> Sign in with Google</span> — do not sign up
              with a new email.
            </p>

            <ol className="mt-4 space-y-3 text-sm text-gray-700 dark:text-gray-300">
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-primary-50 dark:bg-primary-900/40 text-primary-700 dark:text-primary-300 flex items-center justify-center text-xs font-semibold">
                  1
                </span>
                <span>
                  Open{' '}
                  <a
                    href={HOTJAR_URL}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary-600 dark:text-primary-400 hover:underline font-medium"
                  >
                    insights.hotjar.com
                  </a>
                  .
                </span>
              </li>
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-primary-50 dark:bg-primary-900/40 text-primary-700 dark:text-primary-300 flex items-center justify-center text-xs font-semibold">
                  2
                </span>
                <span>
                  Click <span className="font-medium">Sign in with Google</span> and
                  choose one of the shared accounts below.
                </span>
              </li>
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-primary-50 dark:bg-primary-900/40 text-primary-700 dark:text-primary-300 flex items-center justify-center text-xs font-semibold">
                  3
                </span>
                <span>
                  Pick the site (Sunflower, Sunbird Speech, etc.) from the
                  organization switcher in the top-left.
                </span>
              </li>
            </ol>

            <div className="mt-5 grid grid-cols-1 sm:grid-cols-2 gap-3">
              {SIGN_IN_EMAILS.map((email) => (
                <div
                  key={email}
                  className="flex items-center gap-3 p-3 rounded-lg border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-black/20"
                >
                  <div className="p-2 rounded-md bg-primary-50 dark:bg-primary-900/30">
                    <Mail className="w-4 h-4 text-primary-600 dark:text-primary-400" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      Shared Google account
                    </p>
                    <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                      {email}
                    </p>
                  </div>
                </div>
              ))}
            </div>

            <p className="mt-4 text-xs text-gray-500 dark:text-gray-400">
              Credentials are managed in 1Password under <em>Sunbird / Hotjar</em>. If
              you need access, ask an admin to add your email to the shared vault.
            </p>
          </div>
        </div>
      </motion.div>

      {/* What's inside */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
          What you&apos;ll find in Hotjar
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          A quick guide to each tool and the kind of question it answers.
        </p>

        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {FEATURES.map((feature, idx) => (
            <motion.div
              key={feature.name}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.04 }}
              className="bg-white dark:bg-secondary p-5 rounded-xl shadow-sm border border-gray-100 dark:border-white/5 hover:border-primary-500/30 transition-colors group flex flex-col"
            >
              <div
                className={`p-2 rounded-lg w-fit ${feature.color} bg-opacity-10 dark:bg-opacity-20 group-hover:scale-110 transition-transform`}
              >
                <feature.icon
                  className={`w-5 h-5 ${feature.color.replace('bg-', 'text-')}`}
                />
              </div>
              <h3 className="mt-3 text-base font-semibold text-gray-900 dark:text-white">
                {feature.name}
              </h3>
              <p className="mt-2 text-sm text-gray-600 dark:text-gray-300 leading-relaxed">
                {feature.description}
              </p>
              <div className="mt-3 pt-3 border-t border-gray-100 dark:border-white/5">
                <p className="text-xs uppercase tracking-wide text-gray-400 dark:text-gray-500 font-medium">
                  Use it for
                </p>
                <p className="mt-1 text-xs text-gray-600 dark:text-gray-400">
                  {feature.useFor}
                </p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>

      {/* Footer CTA */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-5 rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-black/20">
        <div>
          <p className="text-sm font-medium text-gray-900 dark:text-white">
            Ready to dig in?
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            Open Hotjar in a new tab and pick the product you want to investigate.
          </p>
        </div>
        <a
          href={HOTJAR_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-sm font-medium"
        >
          Go to Hotjar Insights
          <ExternalLink size={16} />
        </a>
      </div>
    </div>
  );
}
