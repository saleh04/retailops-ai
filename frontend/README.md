# RetailOps AI Frontend

The React web client for RetailOps AI. Ask questions in plain language and
review each answer alongside its SQL and query results.

## Run locally

You need Node.js with npm and a running backend. Follow the root
[README setup](../README.md#getting-started) to configure and start the API
first; the frontend expects it at `http://localhost:5000`.

From the repository root, run:

```bash
cd frontend
npm ci
npm run dev
```

Open <http://localhost:5173>.

## API configuration

The default API URL is `http://localhost:5000`. To use another backend, create
`frontend/.env` from the example and set `VITE_API_BASE_URL`:

```bash
cd frontend
cp .env.example .env
```

```dotenv
VITE_API_BASE_URL=http://localhost:5000
```

Restart the Vite server after changing the value. The backend must allow the
frontend's origin in its `CORS_ORIGINS` setting.

## Available commands

| Command | Description |
| --- | --- |
| `npm run dev` | Start the Vite development server with hot reload. |
| `npm run build` | Type-check and create the production bundle in `dist/`. |
| `npm run preview` | Preview the production bundle locally. |
| `npm run typecheck` | Run the TypeScript checks. |

The interface supports saved conversations, follow-up questions, and
expandable SQL, result, and schema details. See the
[backend README](../README.md) for API behavior and the full project setup.
