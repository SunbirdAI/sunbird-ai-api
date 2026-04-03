# Frontend

React + TypeScript + Vite SPA in `frontend/`. Built output goes to `app/static/react_build/` and is served by `app/routers/spa.py`.

## Stack

- **React 18** with TypeScript
- **Vite** for build/dev server
- **Tailwind CSS 3** for styling
- **React Router v6** for client-side routing
- **Chart.js** + react-chartjs-2 for dashboard charts
- **@tanstack/react-table** for data tables
- **Axios** for API calls
- **Sonner** for toast notifications
- **Lucide React** for icons
- **Framer Motion** for animations

## Path Alias

`@` maps to `frontend/src/` (configured in `vite.config.ts` and `tsconfig.json`). Use `@/components/...`, `@/pages/...`, etc.

## Project Structure

```
frontend/src/
├── App.tsx              # Router + providers (AuthProvider, ThemeProvider)
├── main.tsx             # Entry point
├── pages/               # Route-level page components
├── components/          # Shared components (Layout, Header, Footer, etc.)
│   └── ui/              # Primitive UI components (Skeleton, table)
├── context/             # React contexts (AuthContext, ThemeContext)
├── hooks/               # Custom hooks (useDashboardData)
└── lib/                 # Utilities (colors, utils including clsx/tailwind-merge)
```

## Commands

```bash
cd frontend
npm install              # install dependencies
npm run dev              # Vite dev server (hot reload)
npm run build            # TypeScript check + production build → ../app/static/react_build/
npm run watch            # Build in watch mode for backend integration testing
npm run lint             # ESLint check
```

To run Tailwind in watch mode from project root:
```bash
npx tailwindcss -i ./app/static/input.css -o ./app/static/output.css --watch
```

## Auth Pattern

`AuthContext` provides `isAuthenticated`, `isLoading`, `login()`, `logout()`. Protected routes use the `RequireAuth` wrapper in `App.tsx` which redirects to `/login`.

## Routes

| Path | Component | Auth Required |
|------|-----------|---------------|
| `/` | LandingPage | No |
| `/login` | Login | No |
| `/register` | Register | No |
| `/forgot-password` | ForgotPassword | No |
| `/reset-password` | ResetPassword | No |
| `/privacy_policy` | PrivacyPolicy | No |
| `/terms_of_service` | TermsOfService | No |
| `/dashboard` | Dashboard | Yes |
| `/keys` | ApiKeys | Yes |
| `/account` | AccountSettings | Yes |

## Conventions

- Page components live in `pages/`, reusable components in `components/`.
- Use `clsx` + `tailwind-merge` (via `lib/utils.ts`) for conditional class names.
- API calls go through Axios; the backend is the same origin (no CORS in production).
- Theme support (light/dark/system) via `ThemeContext` with `storageKey="sunbird-ui-theme"`.
